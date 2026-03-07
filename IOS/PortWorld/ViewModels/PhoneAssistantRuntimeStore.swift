@MainActor
final class PhoneAssistantRuntimeStore {
  var assistantRuntimeState: AssistantRuntimeState = .inactive
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
