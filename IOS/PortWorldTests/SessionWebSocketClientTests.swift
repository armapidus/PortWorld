import XCTest
@testable import PortWorld

final class SessionWebSocketClientTests: XCTestCase {

  private func makeClient(
    webSocketTaskStateProvider: @escaping SessionWebSocketClient.WebSocketTaskStateProvider = { $0.state },
    reconnectJitterProvider: @escaping SessionWebSocketClient.ReconnectJitterProvider = { Double.random(in: $0) }
  ) -> SessionWebSocketClient {
    SessionWebSocketClient(
      url: URL(string: "wss://example.invalid/ws")!,
      baseReconnectDelayMs: 50,
      maxReconnectDelayMs: 100,
      pingIntervalMs: 1_000,
      webSocketTaskStateProvider: webSocketTaskStateProvider,
      reconnectJitterProvider: reconnectJitterProvider
    )
  }

  func testSetNetworkUnavailablePreventsConnectAndKeepsDisconnectedState() async {
    let client = makeClient()

    await client.setNetworkAvailable(false)
    await client.connect()

    let state = await client.currentState()
    let reconnectAttempts = await client.reconnectAttemptCount()

    XCTAssertEqual(state, .disconnected)
    XCTAssertEqual(reconnectAttempts, 0)

    await client.disconnect()
  }

  func testRestoringNetworkAvailabilityAllowsReconnectFlowIntent() async {
    let client = makeClient()

    await client.setNetworkAvailable(false)
    await client.connect()
    let initialState = await client.currentState()
    XCTAssertEqual(initialState, .disconnected)

    await client.setNetworkAvailable(true)

    let stateAfterRestore = await client.currentState()
    switch stateAfterRestore {
    case .connecting, .connected, .reconnecting:
      XCTAssertTrue(true)
    case .idle, .disconnected:
      XCTFail("Expected reconnect flow intent after restoring network, got \(stateAfterRestore)")
    }

    await client.disconnect()
  }

  func testDisconnectClearsReconnectIntentSoNetworkRestoreDoesNotAutoReconnect() async {
    let client = makeClient()

    await client.setNetworkAvailable(false)
    await client.connect()
    let stateAfterOfflineConnect = await client.currentState()
    XCTAssertEqual(stateAfterOfflineConnect, .disconnected)

    await client.disconnect()
    let stateAfterDisconnect = await client.currentState()
    XCTAssertEqual(stateAfterDisconnect, .disconnected)
    let reconnectAttemptsAfterDisconnect = await client.reconnectAttemptCount()
    XCTAssertEqual(reconnectAttemptsAfterDisconnect, 0)

    await client.setNetworkAvailable(true)

    let restoredState = await client.currentState()
    XCTAssertEqual(
      restoredState,
      .disconnected,
      "Restoring network after an explicit disconnect should not reconnect without new intent."
    )
    let reconnectAttemptsAfterRestore = await client.reconnectAttemptCount()
    XCTAssertEqual(reconnectAttemptsAfterRestore, 0)
  }

  func testEnsureConnectedReArmsReconnectIntentAfterDisconnect() async {
    let client = makeClient()

    await client.setNetworkAvailable(false)
    await client.connect()
    let stateAfterOfflineConnect = await client.currentState()
    XCTAssertEqual(stateAfterOfflineConnect, .disconnected)

    await client.disconnect()
    let stateAfterDisconnect = await client.currentState()
    XCTAssertEqual(stateAfterDisconnect, .disconnected)

    await client.ensureConnected()
    let stateAfterEnsureConnected = await client.currentState()
    XCTAssertEqual(
      stateAfterEnsureConnected,
      .disconnected,
      "While offline, ensureConnected should set reconnect intent without changing disconnected state."
    )

    await client.setNetworkAvailable(true)

    let stateAfterRestore = await client.currentState()
    switch stateAfterRestore {
    case .connecting, .connected, .reconnecting:
      XCTAssertTrue(true)
    case .idle, .disconnected:
      XCTFail("Expected reconnect flow after ensureConnected + network restore, got \(stateAfterRestore)")
    }

    await client.disconnect()
  }

  func testRepeatedOfflineConnectCallsRemainDisconnectedWithoutBackoffAttempts() async {
    let client = makeClient()

    await client.setNetworkAvailable(false)
    await client.connect()
    await client.connect()
    await client.connect()

    let state = await client.currentState()
    let reconnectAttempts = await client.reconnectAttemptCount()
    XCTAssertEqual(state, .disconnected)
    XCTAssertEqual(reconnectAttempts, 0)

    await client.disconnect()
  }

  func testConnectTreatsInjectedCompletedTaskAsStaleAndAttemptsFreshConnection() async {
    let staleTask = URLSession.shared.webSocketTask(with: URL(string: "wss://example.invalid/ws")!)
    let client = makeClient(webSocketTaskStateProvider: { task in
      task === staleTask ? .completed : task.state
    })

    await client.setWebSocketTaskForTesting(staleTask)
    await client.connect()

    let state = await client.currentState()
    XCTAssertEqual(state, .connecting)

    await client.disconnect()
  }

  func testSendIncrementsSequenceOnEveryCall() async {
    struct Payload: Codable {
      let value: Int
    }

    let client = makeClient()
    let task = URLSession.shared.webSocketTask(with: URL(string: "wss://example.invalid/ws")!)
    await client.setWebSocketTaskForTesting(task)

    _ = try? await client.send(type: .queryBundleUploaded, sessionID: "s1", payload: Payload(value: 1))
    _ = try? await client.send(type: .queryBundleUploaded, sessionID: "s1", payload: Payload(value: 2))
    _ = try? await client.send(type: .queryBundleUploaded, sessionID: "s1", payload: Payload(value: 3))

    let sequence = await client.outboundSequenceForTesting()
    XCTAssertEqual(sequence, 3)

    await client.disconnect()
  }

  func testReconnectBackoffIsBoundedAndDeterministicWhenJitterIsInjected() async {
    let deterministicClient = makeClient(reconnectJitterProvider: { _ in 1.0 })
    let deterministicAttempt1 = await deterministicClient.reconnectDelayMsForTesting(attempt: 1)
    let deterministicAttempt2 = await deterministicClient.reconnectDelayMsForTesting(attempt: 2)
    let deterministicAttempt10 = await deterministicClient.reconnectDelayMsForTesting(attempt: 10)
    XCTAssertEqual(deterministicAttempt1, 100)
    XCTAssertEqual(deterministicAttempt2, 100)
    XCTAssertEqual(deterministicAttempt10, 100)

    let minJitterClient = makeClient(reconnectJitterProvider: { _ in 0.8 })
    let minAttempt1 = await minJitterClient.reconnectDelayMsForTesting(attempt: 1)
    let minAttempt6 = await minJitterClient.reconnectDelayMsForTesting(attempt: 6)
    XCTAssertEqual(minAttempt1, 80)
    XCTAssertEqual(minAttempt6, 80)

    let maxJitterClient = makeClient(reconnectJitterProvider: { _ in 1.2 })
    let maxAttempt1 = await maxJitterClient.reconnectDelayMsForTesting(attempt: 1)
    let maxAttempt6 = await maxJitterClient.reconnectDelayMsForTesting(attempt: 6)
    XCTAssertEqual(maxAttempt1, 120)
    XCTAssertEqual(maxAttempt6, 120)
  }
}
