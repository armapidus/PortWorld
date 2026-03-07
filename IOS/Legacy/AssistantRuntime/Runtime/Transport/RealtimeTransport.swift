import Foundation

// Legacy realtime transport contract retained only for the archived assistant runtime.
protocol RealtimeTransport: Sendable {
  var events: AsyncStream<TransportEvent> { get }

  func connect(config: TransportConfig) async throws
  func disconnect() async
  func sendAudio(_ buffer: Data, timestampMs: Int64) async throws
  func sendLiveAudio(_ buffer: Data, timestampMs: Int64) async throws
  func sendProbe(timestampMs: Int64) async throws
  func sendControl(_ message: TransportControlMessage) async throws
  func diagnosticsSnapshot() async -> SessionWebSocketDiagnosticsSnapshot
}

extension RealtimeTransport {
  func sendLiveAudio(_ buffer: Data, timestampMs: Int64) async throws {
    try await sendAudio(buffer, timestampMs: timestampMs)
  }

  func diagnosticsSnapshot() async -> SessionWebSocketDiagnosticsSnapshot {
    SessionWebSocketDiagnosticsSnapshot(
      connectionID: 0,
      lastOutboundKind: "none",
      lastOutboundBytes: 0,
      binarySendAttemptCount: 0,
      binarySendSuccessCount: 0,
      lastBinaryFirstByteHex: "none",
      inboundServerAudioFrameCount: 0,
      inboundServerAudioBytes: 0,
      lastInboundServerAudioBytes: 0,
      lastPlaybackControlCommand: "none"
    )
  }
}
