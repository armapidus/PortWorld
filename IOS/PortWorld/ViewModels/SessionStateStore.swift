import Observation
import SwiftUI

enum StreamingStatus {
  case streaming
  case waiting
  case stopped
}

enum AssistantRuntimeState {
  case inactive
  case activating
  case active
  case deactivating
  case failed
}

enum InternetReachabilityState {
  case unknown
  case connected
  case disconnected
}

@MainActor
@Observable
final class SessionStateStore {
  var currentVideoFrame: UIImage?
  var hasReceivedFirstFrame: Bool = false
  var streamingStatus: StreamingStatus = .stopped
  var showError: Bool = false
  var errorMessage: String = ""
  var hasActiveDevice: Bool = false

  var assistantRuntimeState: AssistantRuntimeState = .inactive
  var runtimeSessionStateText: String = "inactive" {
    didSet {
      updateRealtimePresentationState()
    }
  }
  var runtimeWakeStateText: String = "idle"
  var runtimeQueryStateText: String = "idle"
  var runtimePhotoStateText: String = "idle"
  var runtimePlaybackStateText: String = "idle" {
    didSet {
      updateRealtimePresentationState()
    }
  }
  var internetReachabilityState: InternetReachabilityState = .unknown {
    didSet {
      updateRealtimePresentationState()
    }
  }
  var isInternetReachable: Bool {
    get { internetReachabilityState != .disconnected }
    set { internetReachabilityState = newValue ? .connected : .disconnected }
  }
  var transportStatusText: String = "Disconnected"
  var streamDurationSeconds: Int = 0
  var runtimeWakeEngineText: String = "manual"
  var runtimeWakeRuntimeText: String = "idle"
  var runtimeSpeechAuthorizationText: String = "not_required"
  var runtimeManualWakeFallbackText: String = "enabled"
  var runtimeBackendText: String = "-"
  var runtimeErrorText: String = ""
  var runtimeInfoText: String = ""
  var runtimeWakePhraseText: String = ""
  var runtimeSleepPhraseText: String = ""
  var runtimeSessionIdText: String = "-"
  var runtimeQueryIdText: String = "-"
  var runtimeWakeCount: Int = 0
  var runtimeQueryCount: Int = 0
  var runtimeVideoFrameCount: Int = 0
  var runtimePhotoUploadCount: Int = 0
  var runtimePlaybackChunkCount: Int = 0
  var runtimePendingPlaybackBufferCount: Int = 0

  var audioStateText: String = "idle"
  var audioStatsText: String = "Chunks: 0  Bytes: 0"
  var isAudioReady: Bool = false
  var isAudioRecording: Bool = false
  var audioSessionPath: String = "No audio session directory"
  var audioLastError: String = ""
  var audioChunkCount: Int = 0
  var audioByteCount: Int64 = 0

  var capturedPhoto: UIImage?
  var showPhotoPreview: Bool = false
  private var streamStartedAt: Date?

  var isStreaming: Bool {
    switch assistantRuntimeState {
    case .activating, .active, .deactivating:
      return true
    case .inactive, .failed:
      return false
    }
  }

  var canActivateAssistantRuntime: Bool {
    hasActiveDevice && (assistantRuntimeState == .inactive || assistantRuntimeState == .failed)
  }

  var canDeactivateAssistantRuntime: Bool {
    switch assistantRuntimeState {
    case .activating, .active, .failed:
      return true
    case .inactive, .deactivating:
      return false
    }
  }

  private func updateRealtimePresentationState(now: Date = Date()) {
    if internetReachabilityState == .unknown {
      transportStatusText = "Checking internet"
    } else if !isInternetReachable {
      transportStatusText = "No internet"
    } else {
    let sessionState = runtimeSessionStateText.lowercased()
    let playbackState = runtimePlaybackStateText.lowercased()

    switch sessionState {
    case "reconnecting":
      transportStatusText = "Reconnecting"
    case "connecting", "activating", "waiting":
      transportStatusText = "Connecting"
    case "active":
      if playbackState.contains("buffer") || playbackState.contains("wait") {
        transportStatusText = "Connected | Buffering audio"
      } else if playbackState == "playing" {
        transportStatusText = "Connected | Playing response"
      } else {
        transportStatusText = "Connected"
      }
    case "failed":
      transportStatusText = "Connection failed"
    default:
      transportStatusText = "Disconnected"
    }
    }

    let sessionState = runtimeSessionStateText.lowercased()
    if sessionState == "active" {
      if streamStartedAt == nil {
        streamStartedAt = now
      }
      if let streamStartedAt {
        streamDurationSeconds = max(0, Int(now.timeIntervalSince(streamStartedAt)))
      } else {
        streamDurationSeconds = 0
      }
    } else {
      streamStartedAt = nil
      streamDurationSeconds = 0
    }
  }
}
