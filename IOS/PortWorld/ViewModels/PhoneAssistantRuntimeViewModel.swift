import Combine
import SwiftUI

@MainActor
final class PhoneAssistantRuntimeViewModel: ObservableObject {
  let store: PhoneAssistantRuntimeStore

  private let controller: AssistantRuntimeController

  init(
    store: PhoneAssistantRuntimeStore? = nil
  ) {
    let runtimeStore = store ?? PhoneAssistantRuntimeStore()
    let config = PhoneOnlyRuntimeConfig.load()
    self.store = runtimeStore
    self.controller = AssistantRuntimeController(config: config)
    bindController()
    apply(snapshot: controller.snapshot)
  }

  func activateAssistant() async {
    await controller.activate()
  }

  func deactivateAssistant() async {
    await controller.deactivate()
  }

  func endConversation() async {
    await controller.endConversation()
  }

  func handleScenePhaseChange(_ phase: ScenePhase) {
    controller.handleScenePhaseChange(phase)
  }

  private func bindController() {
    controller.onStatusUpdated = { [weak self] snapshot in
      guard let self else { return }
      self.apply(snapshot: snapshot)
    }
  }

  private func apply(snapshot: AssistantRuntimeController.StatusSnapshot) {
    objectWillChange.send()
    store.assistantRuntimeState = snapshot.assistantRuntimeState
    store.audioStatusText = snapshot.audioStatusText
    store.backendStatusText = snapshot.backendStatusText
    store.wakeStatusText = snapshot.wakeStatusText
    store.wakePhraseText = snapshot.wakePhraseText
    store.sleepPhraseText = snapshot.sleepPhraseText
    store.sessionID = snapshot.sessionID
    store.transportStatusText = snapshot.transportStatusText
    store.uplinkStatusText = snapshot.uplinkStatusText
    store.playbackStatusText = snapshot.playbackStatusText
    store.playbackRouteText = snapshot.playbackRouteText
    store.infoText = snapshot.infoText
    store.errorText = snapshot.errorText
  }
}
