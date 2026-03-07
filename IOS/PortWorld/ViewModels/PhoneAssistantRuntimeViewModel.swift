// View model that bridges assistant runtime actions and published UI status.
import Combine
import SwiftUI

@MainActor
final class PhoneAssistantRuntimeViewModel: ObservableObject {
  @Published private(set) var status: PhoneAssistantRuntimeStatus

  private let controller: AssistantRuntimeController

  init() {
    let config = PhoneOnlyRuntimeConfig.load()
    self.controller = AssistantRuntimeController(config: config)
    self.status = controller.status
    bindController()
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
    controller.onStatusUpdated = { [weak self] status in
      guard let self else { return }
      self.status = status
    }
  }
}
