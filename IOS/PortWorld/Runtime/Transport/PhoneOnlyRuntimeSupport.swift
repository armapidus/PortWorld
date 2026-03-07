// Active phone-only runtime support types that should not depend on legacy transport surfaces.
import Foundation

enum PhoneAssistantRuntimeState: String, Codable, Sendable {
  case inactive
  case armedListening = "armed_listening"
  case connectingConversation = "connecting_conversation"
  case activeConversation = "active_conversation"
  case pausedByHardware = "paused_by_hardware"
  case deactivating
}

enum PhoneOnlyTransportError: Error, LocalizedError, Sendable {
  case notConnected
  case transport(String)
  case decoding(String)
  case encoding(String)

  nonisolated var errorDescription: String? {
    switch self {
    case .notConnected:
      return "WebSocket is not connected."
    case .transport(let message):
      return "WebSocket transport error: \(message)"
    case .decoding(let message):
      return "WebSocket payload decode error: \(message)"
    case .encoding(let message):
      return "WebSocket payload encode error: \(message)"
    }
  }
}

nonisolated struct PhoneOnlyTransportDiagnosticsSnapshot: Sendable, Equatable {
  let connectionID: Int
  let lastOutboundKind: String
  let lastOutboundBytes: Int
  let binarySendAttemptCount: Int
  let binarySendSuccessCount: Int
  let lastBinaryFirstByteHex: String
  let inboundServerAudioFrameCount: Int
  let inboundServerAudioBytes: Int
  let lastInboundServerAudioBytes: Int
  let lastPlaybackControlCommand: String
}

@MainActor
protocol PhoneOnlyAssistantPlaybackControlling: AnyObject {
  var onRouteChanged: ((String) -> Void)? { get set }
  var onRouteIssue: ((String) -> Void)? { get set }
  var pendingBufferCount: Int { get }
  var pendingBufferDurationMs: Double { get }
  var isBackpressured: Bool { get }

  func hasActivePendingPlayback() -> Bool
  func appendPCMData(_ pcmData: Data, format incomingFormat: AssistantAudioFormat) throws
  func handlePlaybackControl(_ payload: PhoneOnlyPlaybackControlPayload)
  func cancelResponse()
  func shutdown()
  func prepareForBackground()
  func restoreFromBackground()
  func currentRouteDescription() -> String
}
