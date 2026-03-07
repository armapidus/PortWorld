// View model that bridges assistant runtime actions and published UI status.
import Combine
import MWDATCore
import SwiftUI

@MainActor
final class PhoneAssistantRuntimeViewModel: ObservableObject {
  @Published private(set) var status: PhoneAssistantRuntimeStatus

  private let controller: AssistantRuntimeController
  private let wearablesRuntimeManager: WearablesRuntimeManager
  private var controllerStatus: PhoneAssistantRuntimeStatus
  private var selectedRoute: AssistantRoute = .phone
  private var cancellables = Set<AnyCancellable>()

  init(wearablesRuntimeManager: WearablesRuntimeManager) {
    self.wearablesRuntimeManager = wearablesRuntimeManager
    let config = PhoneOnlyRuntimeConfig.load()
    self.controller = AssistantRuntimeController(config: config)
    self.controllerStatus = controller.status
    self.status = controller.status
    bindController()
    bindWearablesRuntimeManager()
    publishMergedStatus()
  }

  func activateAssistant() async {
    guard selectedRoute == .phone else { return }
    await controller.activate()
  }

  func deactivateAssistant() async {
    await controller.deactivate()
  }

  func endConversation() async {
    await controller.endConversation()
  }

  func selectRoute(_ route: AssistantRoute) {
    guard controllerStatus.assistantRuntimeState == .inactive else { return }
    guard selectedRoute != route else { return }
    selectedRoute = route
    publishMergedStatus()
  }

  func handleScenePhaseChange(_ phase: ScenePhase) {
    controller.handleScenePhaseChange(phase)
  }

  private func bindController() {
    controller.onStatusUpdated = { [weak self] status in
      guard let self else { return }
      self.controllerStatus = status
      self.publishMergedStatus()
    }
  }

  private func bindWearablesRuntimeManager() {
    wearablesRuntimeManager.$configurationState
      .sink { [weak self] _ in self?.publishMergedStatus() }
      .store(in: &cancellables)

    wearablesRuntimeManager.$configurationErrorMessage
      .sink { [weak self] _ in self?.publishMergedStatus() }
      .store(in: &cancellables)

    wearablesRuntimeManager.$registrationState
      .sink { [weak self] _ in self?.publishMergedStatus() }
      .store(in: &cancellables)

    wearablesRuntimeManager.$devices
      .sink { [weak self] _ in self?.publishMergedStatus() }
      .store(in: &cancellables)

    wearablesRuntimeManager.$activeCompatibilityMessage
      .sink { [weak self] _ in self?.publishMergedStatus() }
      .store(in: &cancellables)
  }

  private func publishMergedStatus() {
    var mergedStatus = controllerStatus
    let readiness = makeGlassesReadiness()

    mergedStatus.selectedRoute = selectedRoute
    mergedStatus.glassesReadinessTitle = readiness.title
    mergedStatus.glassesReadinessDetail = readiness.detail
    mergedStatus.glassesReadinessKind = readiness.kind
    mergedStatus.canActivateSelectedRoute = selectedRoute == .phone
    mergedStatus.activationButtonTitle = selectedRoute == .phone
      ? "Activate Assistant"
      : "Glasses Activation Coming Next"

    status = mergedStatus
  }

  private func makeGlassesReadiness() -> (title: String, detail: String, kind: GlassesReadinessKind) {
    if let compatibilityMessage = wearablesRuntimeManager.activeCompatibilityMessage {
      return (
        "Glasses need attention",
        compatibilityMessage,
        .warning
      )
    }

    switch wearablesRuntimeManager.configurationState {
    case .idle, .configuring:
      return (
        "Initializing glasses support",
        "The app is preparing shared DAT support in the background.",
        .neutral
      )

    case .failed:
      let detail = wearablesRuntimeManager.configurationErrorMessage
        ?? "Wearables SDK initialization failed. Open Glasses Setup to retry."
      return (
        "Glasses unavailable",
        detail,
        .error
      )

    case .ready:
      break
    }

    guard wearablesRuntimeManager.registrationState == .registered else {
      return (
        "Glasses setup required",
        "Meta registration is not complete yet. Open Glasses Setup to connect your glasses.",
        .neutral
      )
    }

    if wearablesRuntimeManager.devices.isEmpty {
      return (
        "Waiting for glasses",
        "Registration is complete, but no compatible glasses are currently discovered.",
        .neutral
      )
    }

    return (
      "Glasses detected",
      "\(wearablesRuntimeManager.devices.count) device(s) available for the next runtime step.",
      .success
    )
  }
}
