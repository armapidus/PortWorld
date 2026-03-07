import Foundation

struct SessionWebSocketDiagnosticsSnapshot: Sendable, Equatable {
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

enum SessionWebSocketClientError: Error, LocalizedError, Sendable, Equatable {
  case notConnected
  case encoding(String)
  case transport(String)

  var errorDescription: String? {
    switch self {
    case .notConnected:
      return "WebSocket is not connected."
    case .encoding(let message):
      return message
    case .transport(let message):
      return message
    }
  }
}

@MainActor
protocol AssistantPlaybackEngineProtocol: AnyObject {
  var onRouteChanged: ((String) -> Void)? { get set }
  var onRouteIssue: ((String) -> Void)? { get set }
  var pendingBufferCount: Int { get }
  var pendingBufferDurationMs: Double { get }
  var isBackpressured: Bool { get }

  func hasActivePendingPlayback() -> Bool
  func appendChunk(_ payload: AssistantAudioChunkPayload) throws
  func appendPCMData(_ pcmData: Data, format incomingFormat: AssistantAudioFormat) throws
  func handlePlaybackControl(_ payload: PlaybackControlPayload)
  func cancelResponse()
  func shutdown()
  func prepareForBackground()
  func restoreFromBackground()
  func currentRouteDescription() -> String
}
