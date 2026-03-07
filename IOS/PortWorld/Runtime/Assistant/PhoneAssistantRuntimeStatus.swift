// Shared UI-facing status model for the phone-only assistant runtime.
import Foundation

enum AssistantRoute: String {
  case phone
  case glasses
}

enum GlassesReadinessKind {
  case neutral
  case success
  case warning
  case error
}

struct PhoneAssistantRuntimeStatus {
  var assistantRuntimeState: PhoneAssistantRuntimeState = .inactive
  var selectedRoute: AssistantRoute = .phone
  var glassesReadinessTitle: String = "Glasses setup required"
  var glassesReadinessDetail: String = "Open Glasses Setup to connect Meta glasses and review DAT readiness."
  var glassesReadinessKind: GlassesReadinessKind = .neutral
  var canActivateSelectedRoute: Bool = true
  var activationButtonTitle: String = "Activate Assistant"
  var audioStatusText: String = "idle"
  var backendStatusText: String = "idle"
  var wakeStatusText: String = "idle"
  var wakePhraseText: String = ""
  var sleepPhraseText: String = ""
  var sessionID: String = "-"
  var transportStatusText: String = "disconnected"
  var uplinkStatusText: String = "idle"
  var playbackStatusText: String = "idle"
  var playbackRouteText: String = "-"
  var infoText: String = ""
  var errorText: String = ""

  var canActivate: Bool {
    assistantRuntimeState == .inactive
  }

  var canChangeRoute: Bool {
    assistantRuntimeState == .inactive
  }

  var canDeactivate: Bool {
    switch assistantRuntimeState {
    case .armedListening, .connectingConversation, .activeConversation:
      return true
    case .inactive, .deactivating:
      return false
    }
  }

  var canEndConversation: Bool {
    switch assistantRuntimeState {
    case .connectingConversation, .activeConversation:
      return true
    case .inactive, .armedListening, .deactivating:
      return false
    }
  }
}
