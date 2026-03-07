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
  private var pendingGlassesActivation = false
  private var isStartingPhoneRuntimeForGlassesRoute = false
  private var isStoppingGlassesRoute = false
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
    guard controllerStatus.assistantRuntimeState == .inactive else { return }

    switch selectedRoute {
    case .phone:
      pendingGlassesActivation = false
      await controller.activate()

    case .glasses:
      guard canActivateGlassesRoute else {
        publishMergedStatus()
        return
      }

      pendingGlassesActivation = true
      publishMergedStatus()
      await wearablesRuntimeManager.startGlassesSession()
      await synchronizeGlassesRouteIfNeeded()
    }

    publishMergedStatus()
  }

  func deactivateAssistant() async {
    if isGlassesRouteOwned {
      pendingGlassesActivation = false
      await controller.deactivate()
      await wearablesRuntimeManager.stopGlassesSession()
    } else {
      await controller.deactivate()
    }

    publishMergedStatus()
  }

  func endConversation() async {
    await controller.endConversation()
  }

  func selectRoute(_ route: AssistantRoute) {
    guard controllerStatus.assistantRuntimeState == .inactive else { return }
    guard pendingGlassesActivation == false else { return }
    guard wearablesRuntimeManager.isGlassesSessionRequested == false else { return }
    guard selectedRoute != route else { return }
    selectedRoute = route
    publishMergedStatus()
  }

  func handleScenePhaseChange(_ phase: ScenePhase) {
    controller.handleScenePhaseChange(phase)
  }

  private var isGlassesRouteOwned: Bool {
    selectedRoute == .glasses &&
      (
        pendingGlassesActivation ||
          wearablesRuntimeManager.isGlassesSessionRequested ||
          controllerStatus.assistantRuntimeState != .inactive
      )
  }

  private var canActivateGlassesRoute: Bool {
    guard controllerStatus.assistantRuntimeState == .inactive else { return false }
    guard pendingGlassesActivation == false else { return false }
    guard wearablesRuntimeManager.isGlassesSessionRequested == false else { return false }
    guard wearablesRuntimeManager.configurationState == .ready else { return false }
    guard wearablesRuntimeManager.registrationState == .registered else { return false }
    guard wearablesRuntimeManager.devices.isEmpty == false else { return false }
    guard wearablesRuntimeManager.activeCompatibilityMessage == nil else { return false }
    guard wearablesRuntimeManager.glassesSessionPhase != .failed else { return false }
    return true
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
      .sink { [weak self] _ in self?.handleWearablesRuntimeManagerChange() }
      .store(in: &cancellables)

    wearablesRuntimeManager.$configurationErrorMessage
      .sink { [weak self] _ in self?.handleWearablesRuntimeManagerChange() }
      .store(in: &cancellables)

    wearablesRuntimeManager.$registrationState
      .sink { [weak self] _ in self?.handleWearablesRuntimeManagerChange() }
      .store(in: &cancellables)

    wearablesRuntimeManager.$devices
      .sink { [weak self] _ in self?.handleWearablesRuntimeManagerChange() }
      .store(in: &cancellables)

    wearablesRuntimeManager.$activeCompatibilityMessage
      .sink { [weak self] _ in self?.handleWearablesRuntimeManagerChange() }
      .store(in: &cancellables)

    wearablesRuntimeManager.$glassesSessionPhase
      .sink { [weak self] _ in self?.handleWearablesRuntimeManagerChange() }
      .store(in: &cancellables)

    wearablesRuntimeManager.$glassesSessionState
      .sink { [weak self] _ in self?.handleWearablesRuntimeManagerChange() }
      .store(in: &cancellables)

    wearablesRuntimeManager.$activeGlassesDeviceName
      .sink { [weak self] _ in self?.publishMergedStatus() }
      .store(in: &cancellables)

    wearablesRuntimeManager.$isGlassesSessionRequested
      .sink { [weak self] _ in self?.handleWearablesRuntimeManagerChange() }
      .store(in: &cancellables)

    wearablesRuntimeManager.$glassesSessionErrorMessage
      .sink { [weak self] _ in self?.handleWearablesRuntimeManagerChange() }
      .store(in: &cancellables)
  }

  private func handleWearablesRuntimeManagerChange() {
    Task { @MainActor [weak self] in
      await self?.synchronizeGlassesRouteIfNeeded()
      self?.publishMergedStatus()
    }
  }

  private func synchronizeGlassesRouteIfNeeded() async {
    guard selectedRoute == .glasses || wearablesRuntimeManager.isGlassesSessionRequested || pendingGlassesActivation ||
      controllerStatus.assistantRuntimeState == .pausedByHardware else {
      return
    }

    let glassesSessionPhase = wearablesRuntimeManager.glassesSessionPhase
    let glassesSessionState = wearablesRuntimeManager.glassesSessionState

    if glassesSessionPhase == .running {
      if pendingGlassesActivation &&
        controllerStatus.assistantRuntimeState == .inactive &&
        isStartingPhoneRuntimeForGlassesRoute == false {
        isStartingPhoneRuntimeForGlassesRoute = true
        pendingGlassesActivation = false
        await controller.activate()
        isStartingPhoneRuntimeForGlassesRoute = false
        return
      }

      if controllerStatus.assistantRuntimeState == .pausedByHardware {
        await controller.resumeFromExternalRoutePause()
        return
      }
    }

    if glassesSessionPhase == .paused {
      switch controllerStatus.assistantRuntimeState {
      case .armedListening, .connectingConversation, .activeConversation:
        await controller.suspendForExternalRoutePause()
        return
      case .inactive, .pausedByHardware, .deactivating:
        break
      }
    }

    if glassesSessionPhase == .failed || glassesSessionState == .stopped {
      guard isStoppingGlassesRoute == false else { return }
      guard pendingGlassesActivation ||
        wearablesRuntimeManager.isGlassesSessionRequested ||
        controllerStatus.assistantRuntimeState != .inactive else {
        return
      }

      isStoppingGlassesRoute = true
      pendingGlassesActivation = false
      if controllerStatus.assistantRuntimeState != .inactive {
        await controller.deactivate()
      }
      await wearablesRuntimeManager.stopGlassesSession()
      isStoppingGlassesRoute = false
    }
  }

  private func publishMergedStatus() {
    var mergedStatus = controllerStatus
    let readiness = makeGlassesReadiness()

    mergedStatus.selectedRoute = selectedRoute
    mergedStatus.activeRouteText = activeRouteText()
    mergedStatus.glassesReadinessTitle = readiness.title
    mergedStatus.glassesReadinessDetail = readiness.detail
    mergedStatus.glassesReadinessKind = readiness.kind
    mergedStatus.glassesSessionText = glassesSessionText()
    mergedStatus.activeGlassesDeviceText = wearablesRuntimeManager.activeGlassesDeviceName
    mergedStatus.canChangeRoute =
      controllerStatus.assistantRuntimeState == .inactive &&
      pendingGlassesActivation == false &&
      wearablesRuntimeManager.isGlassesSessionRequested == false
    mergedStatus.canActivateSelectedRoute = selectedRoute == .phone
      ? controllerStatus.assistantRuntimeState == .inactive
      : canActivateGlassesRoute
    mergedStatus.activationButtonTitle = activationButtonTitle()

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

    guard wearablesRuntimeManager.devices.isEmpty == false else {
      return (
        "Waiting for glasses",
        "Registration is complete, but no compatible glasses are currently discovered.",
        .neutral
      )
    }

    switch wearablesRuntimeManager.glassesSessionPhase {
    case .starting:
      return (
        "Starting glasses session",
        "Requesting a device-owned DAT session before the assistant arms. Audio still uses the phone path in this step.",
        .neutral
      )

    case .waitingForDevice:
      if wearablesRuntimeManager.isGlassesSessionRequested {
        return (
          "Waiting for glasses session",
          "The glasses route is selected, but DAT is still waiting for a device to become available.",
          .warning
        )
      }
      fallthrough

    case .inactive:
      return (
        "Glasses detected",
        "Glasses lifecycle can now activate through DAT. Audio still uses the phone path until the next step.",
        .success
      )

    case .running:
      return (
        "Glasses session live",
        "DAT lifecycle is active for the selected route. Audio still uses the phone path in this step.",
        .success
      )

    case .paused:
      return (
        "Glasses paused",
        "The glasses session is paused by hardware state. The assistant will resume when DAT returns to running.",
        .warning
      )

    case .stopping:
      return (
        "Stopping glasses session",
        "Releasing the current DAT session and returning control to the main runtime.",
        .neutral
      )

    case .failed:
      let detail = wearablesRuntimeManager.glassesSessionErrorMessage
        ?? "The DAT device session failed to start or continue."
      return (
        "Glasses session failed",
        detail,
        .error
      )
    }
  }

  private func activationButtonTitle() -> String {
    switch selectedRoute {
    case .phone:
      return "Activate Assistant"
    case .glasses:
      if pendingGlassesActivation || wearablesRuntimeManager.glassesSessionPhase == .starting {
        return "Starting Glasses Session..."
      }
      return "Activate Glasses Runtime"
    }
  }

  private func activeRouteText() -> String {
    if selectedRoute == .glasses &&
      (
        pendingGlassesActivation ||
          wearablesRuntimeManager.isGlassesSessionRequested ||
          controllerStatus.assistantRuntimeState == .pausedByHardware ||
          controllerStatus.assistantRuntimeState != .inactive
      ) {
      return AssistantRoute.glasses.rawValue
    }

    if controllerStatus.assistantRuntimeState != .inactive {
      return AssistantRoute.phone.rawValue
    }

    return "none"
  }

  private func glassesSessionText() -> String {
    if let sessionState = wearablesRuntimeManager.glassesSessionState {
      return sessionState.description
    }
    return wearablesRuntimeManager.glassesSessionPhase.rawValue
  }
}
