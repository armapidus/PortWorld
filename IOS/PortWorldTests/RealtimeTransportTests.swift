import XCTest
@testable import PortWorld

final class RealtimeTransportTests: XCTestCase {

  func testConnectSendTenFramesReceiveTenEchoedFramesThenDisconnect() async throws {
    let transport = MockRealtimeTransport(echoAudioOnSend: true)
    let harness = RealtimeSessionHarness(transport: transport)
    registerHarnessTeardown(harness)

    try await harness.start(config: Self.makeConfig())

    try await assertEventually {
      harness.currentState() == .connected
    }

    for index in 0..<10 {
      let payload = Data([UInt8(index), UInt8((index + 1) % 255)])
      try await harness.sendAudio(payload, timestampMs: Int64(index * 20))
    }

    try await assertEventually {
      harness.receivedAudioCount() == 10
    }

    await harness.stop()

    let connectCallCount = await transport.connectCallCount()
    let sentAudioCount = await transport.sentAudioCount()
    let disconnectCallCount = await transport.disconnectCallCount()
    let reconnectIntentCount = harness.reconnectIntentCount()
    XCTAssertEqual(connectCallCount, 1)
    XCTAssertEqual(sentAudioCount, 10)
    XCTAssertEqual(disconnectCallCount, 1)
    XCTAssertEqual(reconnectIntentCount, 0)

    let sent = await transport.sentAudioFrames()
    let echoed = harness.receivedAudioFrames()
    XCTAssertEqual(sent.map(\.timestampMs), echoed.map(\.timestampMs))
    XCTAssertEqual(sent.map(\.buffer), echoed.map(\.payload))
  }

  func testConnectThenTransportDropTriggersAutoReconnectAndResumeIntent() async throws {
    let transport = MockRealtimeTransport(echoAudioOnSend: false)
    let harness = RealtimeSessionHarness(transport: transport)
    registerHarnessTeardown(harness)

    try await harness.start(config: Self.makeConfig())

    try await assertEventually {
      harness.currentState() == .connected
    }

    await transport.simulateDrop()

    try await assertEventually(timeout: 6.0) {
      await transport.connectCallCount() == 2
    }

    let reconnectIntentCount = harness.reconnectIntentCount()
    let currentState = harness.currentState()
    XCTAssertEqual(reconnectIntentCount, 1)
    XCTAssertEqual(currentState, .connected)

    try await harness.sendAudio(Data([0xAA, 0xBB]), timestampMs: 99)

    try await assertEventually {
      await transport.sentAudioCount() == 1
    }
  }

  func testSleepWordDrivenGracefulDisconnectPreventsReconnect() async throws {
    let transport = MockRealtimeTransport(echoAudioOnSend: false)
    let harness = RealtimeSessionHarness(transport: transport)
    registerHarnessTeardown(harness)

    try await harness.start(config: Self.makeConfig())

    try await assertEventually {
      harness.currentState() == .connected
    }

    try await harness.handleSleepWordDetected()

    try await assertEventually {
      await transport.disconnectCallCount() == 1
    }

    let sentSleepControlCount = await transport.sentControlCount(messageType: "control.sleep_word_detected")
    let reconnectIntentCount = harness.reconnectIntentCount()
    XCTAssertEqual(sentSleepControlCount, 1)
    XCTAssertEqual(reconnectIntentCount, 0)

    await transport.simulateDrop()

    try await assertEventually {
      await transport.connectCallCount() == 1
    }
  }

  private static func makeConfig() -> TransportConfig {
    TransportConfig(
      endpoint: URL(string: "wss://example.invalid/ws")!,
      sessionId: "sess_test_realtime_transport",
      audioFormat: AudioStreamFormat(sampleRate: 16_000, channels: 1, encoding: "pcm_s16le"),
      headers: ["Authorization": "Bearer test"]
    )
  }

  private func assertEventually(
    timeout: TimeInterval = 3.0,
    pollIntervalNs: UInt64 = 20_000_000,
    condition: @escaping () async -> Bool,
    file: StaticString = #filePath,
    line: UInt = #line
  ) async throws {
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
      if await condition() {
        return
      }
      try await Task.sleep(nanoseconds: pollIntervalNs)
    }

    XCTFail("Condition not met within \(timeout)s", file: file, line: line)
  }

  private func registerHarnessTeardown(_ harness: RealtimeSessionHarness) {
    addTeardownBlock {
      await harness.stop()
    }
  }

}

@MainActor
private final class RealtimeSessionHarness {
  private let transport: any RealtimeTransport
  private var eventTask: Task<Void, Never>?
  private var config: TransportConfig?
  private var wantsStreaming = false
  private var state: TransportState = .disconnected
  private var reconnectIntents = 0

  struct ReceivedAudio: Equatable {
    let payload: Data
    let timestampMs: Int64
  }

  private var receivedAudio: [ReceivedAudio] = []

  init(transport: any RealtimeTransport) {
    self.transport = transport
  }

  func start(config: TransportConfig) async throws {
    self.config = config
    self.wantsStreaming = true
    bindEventsIfNeeded()
    try await transport.connect(config: config)
  }

  func stop() async {
    wantsStreaming = false
    await transport.disconnect()
    eventTask?.cancel()
    eventTask = nil
  }

  func sendAudio(_ buffer: Data, timestampMs: Int64) async throws {
    guard state == .connected else { return }
    try await transport.sendAudio(buffer, timestampMs: timestampMs)
  }

  func handleSleepWordDetected() async throws {
    wantsStreaming = false
    try await transport.sendControl(
      TransportControlMessage(
        type: "control.sleep_word_detected",
        payload: ["source": .string("test")]
      )
    )
    await transport.disconnect()
  }

  func currentState() -> TransportState {
    state
  }

  func reconnectIntentCount() -> Int {
    reconnectIntents
  }

  func receivedAudioCount() -> Int {
    receivedAudio.count
  }

  func receivedAudioFrames() -> [ReceivedAudio] {
    receivedAudio
  }

  private func bindEventsIfNeeded() {
    guard eventTask == nil else { return }

    eventTask = Task { [weak self] in
      guard let self else { return }
      for await event in self.transport.events {
        await self.handle(event)
      }
    }
  }

  private func handle(_ event: TransportEvent) async {
    switch event {
    case .audioReceived(let payload, let timestampMs):
      receivedAudio.append(ReceivedAudio(payload: payload, timestampMs: timestampMs))

    case .stateChanged(let newState):
      state = newState
      if newState == .disconnected, wantsStreaming {
        await attemptReconnect()
      }

    case .error(let error):
      // Reconnect intent is driven by disconnected state transitions.
      // Transport implementations may emit both `.stateChanged(.disconnected)`
      // and `.error(.disconnected)` for the same drop event.
      _ = error

    case .closed:
      break

    case .controlReceived:
      break
    }
  }

  private func attemptReconnect() async {
    guard let config else { return }
    reconnectIntents += 1
    do {
      try await transport.connect(config: config)
    } catch {
      // Intentionally ignored in tests; this harness validates reconnect intent.
    }
  }
}

private actor MockRealtimeTransport: RealtimeTransport {
  struct SentAudio: Equatable {
    let buffer: Data
    let timestampMs: Int64
  }

  private(set) var connectConfigs: [TransportConfig] = []
  private(set) var disconnectCount = 0
  private(set) var sentAudio: [SentAudio] = []
  private(set) var sentControls: [TransportControlMessage] = []
  private(set) var sentControlTypes: [String] = []
  private var isConnected = false
  private let echoAudioOnSend: Bool

  let events: AsyncStream<TransportEvent>
  private let continuation: AsyncStream<TransportEvent>.Continuation

  init(echoAudioOnSend: Bool) {
    self.echoAudioOnSend = echoAudioOnSend

    var continuationRef: AsyncStream<TransportEvent>.Continuation!
    self.events = AsyncStream { continuation in
      continuationRef = continuation
    }
    self.continuation = continuationRef
  }

  func connect(config: TransportConfig) async throws {
    connectConfigs.append(config)
    continuation.yield(.stateChanged(.connecting))
    isConnected = true
    continuation.yield(.stateChanged(.connected))
  }

  func disconnect() async {
    disconnectCount += 1
    isConnected = false
    continuation.yield(.stateChanged(.disconnected))
  }

  func sendAudio(_ buffer: Data, timestampMs: Int64) async throws {
    sentAudio.append(SentAudio(buffer: buffer, timestampMs: timestampMs))

    if echoAudioOnSend, isConnected {
      continuation.yield(.audioReceived(buffer, timestampMs: timestampMs))
    }
  }

  func sendProbe(timestampMs: Int64) async throws {
    _ = timestampMs
  }

  func sendControl(_ message: TransportControlMessage) async throws {
    let messageType = message.type
    sentControls.append(message)
    sentControlTypes.append(messageType)
  }

  func simulateDrop() {
    isConnected = false
    continuation.yield(.stateChanged(.disconnected))
    continuation.yield(.error(.disconnected))
  }

  func connectCallCount() -> Int {
    connectConfigs.count
  }

  func disconnectCallCount() -> Int {
    disconnectCount
  }

  func sentAudioCount() -> Int {
    sentAudio.count
  }

  func sentControlCount(messageType: String) async -> Int {
    sentControlTypes.filter { $0 == messageType }.count
  }

  func sentAudioFrames() -> [SentAudio] {
    sentAudio
  }
}
