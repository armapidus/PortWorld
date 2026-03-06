import XCTest
@testable import PortWorld

final class GatewayTransportTests: XCTestCase {

  func testConnectEmitsConnectingThenConnectedWhenMockStateCallbacksInvoked() async throws {
    let webSocket = MockSessionWebSocketClient()
    let transport = GatewayTransport(webSocketClient: webSocket)

    var states: [TransportState] = []
    let eventsExpectation = expectation(description: "receives connecting and connected")
    eventsExpectation.expectedFulfillmentCount = 2

    let eventsTask = Task {
      for await event in transport.events {
        guard case .stateChanged(let state) = event else { continue }
        states.append(state)
        eventsExpectation.fulfill()
        if states.count == 2 { break }
      }
    }

    try await transport.connect(config: Self.makeConfig())
    await webSocket.emitState(.connecting)
    await webSocket.emitState(.connected)

    await fulfillment(of: [eventsExpectation], timeout: 1.0)
    eventsTask.cancel()

    XCTAssertEqual(states.count, 2)
    XCTAssertTrue(states.contains(.connecting))
    XCTAssertTrue(states.contains(.connected))
  }

  func testRawBinaryServerAudioFrameProducesAudioReceivedEvent() async throws {
    let webSocket = MockSessionWebSocketClient()
    let transport = GatewayTransport(webSocketClient: webSocket)

    var receivedPayload = Data()
    var receivedTimestamp: Int64 = 0
    let eventExpectation = expectation(description: "receives audioReceived")

    let eventsTask = Task {
      for await event in transport.events {
        guard case .audioReceived(let payload, let timestampMs) = event else { continue }
        receivedPayload = payload
        receivedTimestamp = timestampMs
        eventExpectation.fulfill()
        break
      }
    }

    try await transport.connect(config: Self.makeConfig())

    let expectedPayload = Data([0x10, 0x20, 0x30])
    let expectedTs: Int64 = 123_456
    let encoded = TransportBinaryFrameCodec.encode(
      TransportBinaryFrame(
        frameType: .serverAudio,
        timestampMs: expectedTs,
        payload: expectedPayload
      )
    )
    await webSocket.emitRaw(.binary(encoded))

    await fulfillment(of: [eventExpectation], timeout: 1.0)
    eventsTask.cancel()

    XCTAssertEqual(receivedPayload, expectedPayload)
    XCTAssertEqual(receivedTimestamp, expectedTs)
  }

  func testSendAudioWritesClientBinaryFrameTypeToRawSentData() async throws {
    let webSocket = MockSessionWebSocketClient()
    let transport = GatewayTransport(webSocketClient: webSocket)

    let connectedExpectation = expectation(description: "transport reaches connected")
    let eventsTask = Task {
      for await event in transport.events {
        guard case .stateChanged(let state) = event, state == .connected else { continue }
        connectedExpectation.fulfill()
        break
      }
    }

    try await transport.connect(config: Self.makeConfig())
    await webSocket.emitState(.connected)
    await fulfillment(of: [connectedExpectation], timeout: 1.0)
    eventsTask.cancel()

    let payload = Data([0x01, 0x02, 0x03, 0x04])
    let timestamp: Int64 = 42
    try await transport.sendAudio(payload, timestampMs: timestamp)

    let sentData = await webSocket.lastSentData()
    let sent = try XCTUnwrap(sentData)
    XCTAssertEqual(sent.first, TransportBinaryFraming.clientAudioTypeByte)

    let decoded = try TransportBinaryFrameCodec.decode(sent)
    XCTAssertEqual(decoded.frameType, .clientAudio)
    XCTAssertEqual(decoded.timestampMs, timestamp)
    XCTAssertEqual(decoded.payload, payload)
  }

  func testSendLiveAudioWritesClientBinaryFrameTypeToRawSentData() async throws {
    let webSocket = MockSessionWebSocketClient()
    let transport = GatewayTransport(webSocketClient: webSocket)
    try await transport.connect(config: Self.makeConfig())

    let payload = Data([0xAA, 0xBB, 0xCC])
    let timestamp: Int64 = 314
    try await transport.sendLiveAudio(payload, timestampMs: timestamp)

    let sentData = await webSocket.lastSentData()
    let sent = try XCTUnwrap(sentData)
    XCTAssertEqual(sent.first, TransportBinaryFraming.clientAudioTypeByte)

    let decoded = try TransportBinaryFrameCodec.decode(sent)
    XCTAssertEqual(decoded.frameType, .clientAudio)
    XCTAssertEqual(decoded.timestampMs, timestamp)
    XCTAssertEqual(decoded.payload, payload)

    let sentText = await webSocket.lastSentText()
    XCTAssertNil(sentText)
  }

  func testSendProbeWritesClientProbeFrameTypeToRawSentData() async throws {
    let webSocket = MockSessionWebSocketClient()
    let transport = GatewayTransport(webSocketClient: webSocket)
    try await transport.connect(config: Self.makeConfig())

    try await transport.sendProbe(timestampMs: 77)

    let sentData = await webSocket.lastSentData()
    let unwrappedData = try XCTUnwrap(sentData)
    let decoded = try TransportBinaryFrameCodec.decode(unwrappedData)
    XCTAssertEqual(decoded.frameType, .clientProbe)
    XCTAssertEqual(decoded.timestampMs, 77)
    XCTAssertEqual(decoded.payload, Data([0x50, 0x57, 0x50, 0x31]))
  }

  func testSendControlWritesTextPayloadContainingControlType() async throws {
    let webSocket = MockSessionWebSocketClient()
    let transport = GatewayTransport(webSocketClient: webSocket)
    try await transport.connect(config: Self.makeConfig())

    let controlType = "control.sleep_word_detected"
    try await transport.sendControl(
      TransportControlMessage(
        type: controlType,
        payload: ["source": .string("test")]
      )
    )

    let lastSentText = await webSocket.lastSentText()
    let sentText = try XCTUnwrap(lastSentText)
    XCTAssertTrue(sentText.contains(controlType))

    let data = try XCTUnwrap(sentText.data(using: .utf8))
    let decoded = try WSMessageCodec.decodeRawEnvelope(from: data)
    XCTAssertEqual(decoded.type, controlType)
  }

  func testTextControlFramesPreserveRealtimeUplinkAckType() async throws {
    let webSocket = MockSessionWebSocketClient()
    let transport = GatewayTransport(webSocketClient: webSocket)

    var receivedControl: TransportControlMessage?
    let eventExpectation = expectation(description: "receives transport uplink ack")

    let eventsTask = Task {
      for await event in transport.events {
        guard case .controlReceived(let control) = event else { continue }
        guard control.type == "transport.uplink.ack" else { continue }
        receivedControl = control
        eventExpectation.fulfill()
        break
      }
    }

    try await transport.connect(config: Self.makeConfig())
    await webSocket.emitRaw(
      .text(
        """
        {"type":"transport.uplink.ack","session_id":"sess_test","seq":1,"ts_ms":123,"payload":{"frames_received":1,"bytes_received":4}}
        """
      )
    )

    await fulfillment(of: [eventExpectation], timeout: 1.0)
    eventsTask.cancel()

    XCTAssertEqual(receivedControl?.type, "transport.uplink.ack")
  }

  func testCloseCallbackEmitsClosedTransportEvent() async throws {
    let webSocket = MockSessionWebSocketClient()
    let transport = GatewayTransport(webSocketClient: webSocket)

    var receivedCloseInfo: TransportSocketCloseInfo?
    let expectation = expectation(description: "receives close event")
    let eventsTask = Task {
      for await event in transport.events {
        guard case .closed(let closeInfo) = event else { continue }
        receivedCloseInfo = closeInfo
        expectation.fulfill()
        break
      }
    }

    try await transport.connect(config: Self.makeConfig())
    await webSocket.emitClose(TransportSocketCloseInfo(connectionID: 3, code: 1001, reason: "test"))

    await fulfillment(of: [expectation], timeout: 1.0)
    eventsTask.cancel()

    XCTAssertEqual(receivedCloseInfo, TransportSocketCloseInfo(connectionID: 3, code: 1001, reason: "test"))
  }

  private static func makeConfig() -> TransportConfig {
    TransportConfig(
      endpoint: URL(string: "wss://example.invalid/ws")!,
      sessionId: "sess_test",
      audioFormat: AudioStreamFormat(sampleRate: 24_000, channels: 1, encoding: "pcm_s16le"),
      headers: ["Authorization": "Bearer test"]
    )
  }
}

private actor MockSessionWebSocketClient: SessionWebSocketClientProtocol {
  private var onStateChange: SessionWebSocketStateHandler?
  private var onRawMessage: SessionWebSocketRawMessageHandler?
  private var onClose: SessionWebSocketCloseHandler?
  private(set) var sentTexts: [String] = []
  private(set) var sentData: [Data] = []

  func bindHandlers(
    onStateChange: SessionWebSocketStateHandler?,
    onMessage: SessionWebSocketMessageHandler?,
    onClose: SessionWebSocketCloseHandler?,
    onError: SessionWebSocketErrorHandler?,
    eventLogger: EventLoggerProtocol?
  ) {
    self.onStateChange = onStateChange
    self.onClose = onClose
  }

  func bindRawMessageHandler(_ onRawMessage: SessionWebSocketRawMessageHandler?) {
    self.onRawMessage = onRawMessage
  }

  func setNetworkAvailable(_ isAvailable: Bool) {}

  func connect() {}

  func disconnect(closeCode: URLSessionWebSocketTask.CloseCode) {}

  func ensureConnected() {}

  func reconnectAttemptCount() -> Int { 0 }

  func sendText(_ text: String) async throws {
    sentTexts.append(text)
  }

  func sendData(_ data: Data) async throws {
    sentData.append(data)
  }

  func send<Payload: Codable>(type: WSOutboundType, sessionID: String, payload: Payload) async throws {}

  func emitState(_ state: SessionWebSocketConnectionState) {
    onStateChange?(state)
  }

  func emitRaw(_ message: SessionWebSocketRawMessage) {
    onRawMessage?(message)
  }

  func emitClose(_ closeInfo: TransportSocketCloseInfo) {
    onClose?(closeInfo)
  }

  func lastSentText() -> String? {
    sentTexts.last
  }

  func lastSentData() -> Data? {
    sentData.last
  }
}
