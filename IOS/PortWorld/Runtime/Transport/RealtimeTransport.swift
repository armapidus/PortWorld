import Foundation

protocol RealtimeTransport: Sendable {
  var events: AsyncStream<TransportEvent> { get }

  func connect(config: TransportConfig) async throws
  func disconnect() async
  func sendAudio(_ buffer: Data, timestampMs: Int64) async throws
  func sendLiveAudio(_ buffer: Data, timestampMs: Int64) async throws
  func sendProbe(timestampMs: Int64) async throws
  func sendControl(_ message: TransportControlMessage) async throws
}

extension RealtimeTransport {
  func sendLiveAudio(_ buffer: Data, timestampMs: Int64) async throws {
    try await sendAudio(buffer, timestampMs: timestampMs)
  }
}
