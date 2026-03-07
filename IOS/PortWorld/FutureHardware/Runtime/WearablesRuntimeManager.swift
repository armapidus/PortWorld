// Shared app-scoped owner for DAT configuration, registration, discovery, and mock-device state.
import Combine
import Foundation
import MWDATCore

@MainActor
final class WearablesRuntimeManager: ObservableObject {
  enum ConfigurationState: Equatable {
    case idle
    case configuring
    case ready
    case failed
  }

  @Published private(set) var configurationState: ConfigurationState = .idle
  @Published private(set) var configurationErrorMessage: String?
  @Published private(set) var configurationDiagnostics: [String] = []
  @Published private(set) var registrationState: RegistrationState?
  @Published private(set) var devices: [DeviceIdentifier] = []
  @Published private(set) var activeCompatibilityMessage: String?
  @Published private(set) var glassesSessionPhase: GlassesSessionPhase = .inactive
  @Published private(set) var glassesSessionState: SessionState?
  @Published private(set) var activeGlassesDeviceName: String = "-"
  @Published private(set) var isGlassesSessionRequested: Bool = false
  @Published private(set) var glassesSessionErrorMessage: String?
  @Published var showError: Bool = false
  @Published var errorMessage: String = ""
  @Published private(set) var isMockModeEnabled: Bool
  @Published private(set) var isMockDeviceReady: Bool
  @Published private(set) var isPreparingMockDevice: Bool

  private let configure: () throws -> Void
  private let wearablesProvider: () -> WearablesInterface
  private let mockDeviceController: MockDeviceController
  private var wearables: WearablesInterface?
  private var glassesSessionCoordinator: GlassesSessionCoordinator?
  private var registrationTask: Task<Void, Never>?
  private var deviceStreamTask: Task<Void, Never>?
  private var compatibilityListenerTokens: [DeviceIdentifier: AnyListenerToken] = [:]
  private var compatibilityMessages: [DeviceIdentifier: String] = [:]

  #if DEBUG
    private let mockModePreferenceKey = "portworld.debug.mockModeEnabled"
  #endif

  init(
    configure: @escaping () throws -> Void = { try Wearables.configure() },
    wearablesProvider: @escaping () -> WearablesInterface = { Wearables.shared },
    mockDeviceController: MockDeviceController? = nil
  ) {
    self.configure = configure
    self.wearablesProvider = wearablesProvider
    self.mockDeviceController = mockDeviceController ?? MockDeviceController()
    self.isMockModeEnabled = false
    self.isMockDeviceReady = self.mockDeviceController.isEnabled
    self.isPreparingMockDevice = false
  }

  deinit {
    registrationTask?.cancel()
    deviceStreamTask?.cancel()
  }

  func startIfNeeded() async {
    switch configurationState {
    case .configuring, .ready, .failed:
      return
    case .idle:
      await configureWearables(forceRetry: false)
    }
  }

  func retryConfiguration() async {
    await configureWearables(forceRetry: true)
  }

  func connectGlasses() {
    guard registrationState != .registering else { return }

    Task { @MainActor [weak self] in
      guard let self else { return }
      if self.configurationState != .ready {
        await self.startIfNeeded()
      }
      guard let wearables = self.wearables else {
        self.presentError(self.configurationErrorMessage ?? "Wearables SDK is not configured.")
        return
      }

      do {
        try await wearables.startRegistration()
      } catch let error as RegistrationError {
        self.presentError(error.description)
      } catch {
        self.presentError(error.localizedDescription)
      }
    }
  }

  func disconnectGlasses() {
    Task { @MainActor [weak self] in
      guard let self else { return }
      await self.stopGlassesSession()
      guard let wearables = self.wearables else {
        self.presentError(self.configurationErrorMessage ?? "Wearables SDK is not configured.")
        return
      }

      do {
        try await wearables.startUnregistration()
      } catch let error as UnregistrationError {
        self.presentError(error.description)
      } catch {
        self.presentError(error.localizedDescription)
      }
    }
  }

  func handleIncomingURL(_ url: URL) async {
    guard Self.isMetaWearablesCallback(url) else { return }

    if configurationState != .ready {
      await configureWearables(forceRetry: configurationState == .failed)
    }

    guard let wearables else {
      presentError(configurationErrorMessage ?? "Wearables SDK is not configured.")
      return
    }

    do {
      _ = try await wearables.handleUrl(url)
    } catch {
      presentError(error.localizedDescription)
    }
  }

  func toggleMockMode() async {
    if isMockModeEnabled {
      disableMockMode()
    } else {
      await enableMockMode()
    }
  }

  func dismissError() {
    errorMessage = ""
    showError = false
  }

  func startGlassesSession() async {
    if configurationState != .ready {
      await startIfNeeded()
    }

    guard configurationState == .ready else {
      glassesSessionErrorMessage = configurationErrorMessage ?? "Wearables SDK is not configured."
      return
    }

    guard registrationState == .registered else {
      glassesSessionErrorMessage = "Meta registration is not complete yet."
      return
    }

    guard devices.isEmpty == false else {
      glassesSessionErrorMessage = "No compatible glasses are currently available."
      return
    }

    guard activeCompatibilityMessage == nil else {
      glassesSessionErrorMessage = activeCompatibilityMessage
      return
    }

    guard let glassesSessionCoordinator else {
      glassesSessionErrorMessage = "Glasses session support is not ready yet."
      return
    }

    isGlassesSessionRequested = true
    glassesSessionErrorMessage = nil

    do {
      try await glassesSessionCoordinator.start()
    } catch {
      isGlassesSessionRequested = false
      glassesSessionErrorMessage = error.localizedDescription
    }
  }

  func stopGlassesSession() async {
    isGlassesSessionRequested = false
    guard let glassesSessionCoordinator else {
      resetGlassesSessionSnapshot()
      return
    }

    await glassesSessionCoordinator.stop()
    glassesSessionErrorMessage = nil
  }

  private func configureWearables(forceRetry: Bool) async {
    switch configurationState {
    case .configuring:
      return
    case .ready where forceRetry == false:
      return
    case .failed where forceRetry == false:
      return
    case .idle, .ready, .failed:
      break
    }

    configurationState = .configuring
    configurationErrorMessage = nil
    configurationDiagnostics = []
    activeCompatibilityMessage = nil
    compatibilityMessages.removeAll(keepingCapacity: false)

    if forceRetry {
      registrationTask?.cancel()
      registrationTask = nil
      deviceStreamTask?.cancel()
      deviceStreamTask = nil
      compatibilityListenerTokens.removeAll(keepingCapacity: false)
      glassesSessionCoordinator = nil
      wearables = nil
      registrationState = nil
      devices = []
      resetGlassesSessionSnapshot()
    }

    do {
      try configure()
      let wearables = wearablesProvider()
      self.wearables = wearables
      registrationState = wearables.registrationState
      devices = wearables.devices
      configurationState = .ready
      observeWearablesStreams(using: wearables)
      monitorDeviceCompatibility(devices: wearables.devices)
      ensureGlassesSessionCoordinator(using: wearables)

      #if DEBUG
        if UserDefaults.standard.bool(forKey: mockModePreferenceKey), isMockModeEnabled == false {
          await enableMockMode()
        }
      #endif
    } catch {
      wearables = nil
      registrationState = nil
      devices = []
      configurationState = .failed
      configurationErrorMessage = error.localizedDescription
      configurationDiagnostics = Self.buildInitializationDiagnostics(from: error)
      glassesSessionCoordinator = nil
      resetGlassesSessionSnapshot()
    }
  }

  private func observeWearablesStreams(using wearables: WearablesInterface) {
    registrationTask?.cancel()
    registrationTask = Task { [weak self] in
      guard let self else { return }
      for await state in wearables.registrationStateStream() {
        self.registrationState = state
        if state != .registered {
          await self.stopGlassesSession()
        }
      }
    }

    deviceStreamTask?.cancel()
    deviceStreamTask = Task { [weak self] in
      guard let self else { return }
      for await devices in wearables.devicesStream() {
        self.devices = devices
        self.monitorDeviceCompatibility(devices: devices)
      }
    }
  }

  private func monitorDeviceCompatibility(devices: [DeviceIdentifier]) {
    guard let wearables else { return }

    let deviceSet = Set(devices)
    compatibilityListenerTokens = compatibilityListenerTokens.filter { entry in
      if deviceSet.contains(entry.key) {
        return true
      }
      compatibilityMessages[entry.key] = nil
      return false
    }
    updateActiveCompatibilityMessage()

    for deviceID in devices {
      guard compatibilityListenerTokens[deviceID] == nil else { continue }
      guard let device = wearables.deviceForIdentifier(deviceID) else { continue }

      let deviceName = device.nameOrId()
      let token = device.addCompatibilityListener { [weak self] compatibility in
        Task { @MainActor [weak self] in
          guard let self else { return }
          if compatibility == .deviceUpdateRequired {
            let message = "Device '\(deviceName)' requires an update to work with this app"
            self.compatibilityMessages[deviceID] = message
            self.updateActiveCompatibilityMessage()
            self.presentError(message)
          } else {
            self.compatibilityMessages[deviceID] = nil
            self.updateActiveCompatibilityMessage()
          }
        }
      }
      compatibilityListenerTokens[deviceID] = token
    }
  }

  private func updateActiveCompatibilityMessage() {
    activeCompatibilityMessage = devices.compactMap { compatibilityMessages[$0] }.first
  }

  private func ensureGlassesSessionCoordinator(using wearables: WearablesInterface) {
    guard glassesSessionCoordinator == nil else { return }

    let coordinator = GlassesSessionCoordinator(wearables: wearables)
    coordinator.onSnapshotUpdated = { [weak self] snapshot in
      guard let self else { return }
      self.applyGlassesSessionSnapshot(snapshot)
    }
    glassesSessionCoordinator = coordinator
  }

  private func applyGlassesSessionSnapshot(_ snapshot: GlassesSessionCoordinator.Snapshot) {
    glassesSessionPhase = snapshot.phase
    glassesSessionState = snapshot.sessionState
    activeGlassesDeviceName = snapshot.activeDeviceName
    if let errorMessage = snapshot.errorMessage {
      glassesSessionErrorMessage = errorMessage
    } else if snapshot.phase != .failed {
      glassesSessionErrorMessage = nil
    }
  }

  private func resetGlassesSessionSnapshot() {
    glassesSessionPhase = .inactive
    glassesSessionState = nil
    activeGlassesDeviceName = "-"
    isGlassesSessionRequested = false
    glassesSessionErrorMessage = nil
  }

  private func enableMockMode() async {
    guard !isPreparingMockDevice else { return }
    isPreparingMockDevice = true
    defer { isPreparingMockDevice = false }

    do {
      try await mockDeviceController.enableMockDevice()
      isMockModeEnabled = true
      isMockDeviceReady = mockDeviceController.isEnabled
      #if DEBUG
        UserDefaults.standard.set(true, forKey: mockModePreferenceKey)
      #endif
    } catch {
      isMockModeEnabled = false
      isMockDeviceReady = false
      #if DEBUG
        UserDefaults.standard.set(false, forKey: mockModePreferenceKey)
      #endif
      presentError("Unable to enable mock device: \(error.localizedDescription)")
    }
  }

  private func disableMockMode() {
    mockDeviceController.disableMockDevice()
    isMockModeEnabled = false
    isMockDeviceReady = mockDeviceController.isEnabled
    #if DEBUG
      UserDefaults.standard.set(false, forKey: mockModePreferenceKey)
    #endif
  }

  private func presentError(_ message: String) {
    errorMessage = message
    showError = true
  }

  private static func isMetaWearablesCallback(_ url: URL) -> Bool {
    guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
      return false
    }
    return components.queryItems?.contains(where: { $0.name == "metaWearablesAction" }) == true
  }

  private static func buildInitializationDiagnostics(from error: Error) -> [String] {
    let nsError = error as NSError
    var diagnostics = [
      "Confirm the Meta AI app is installed and developer mode is enabled for this build.",
      "Verify `MWDAT.AppLinkURLScheme` and `MWDAT.MetaAppID` values in `Info.plist` (`MetaAppID=0` is valid for developer mode).",
      "Check that Bluetooth is enabled and your glasses can be discovered by the phone.",
      "Retry initialization after correcting the issue."
    ]

    #if DEBUG
      diagnostics.append("Debug details: domain=\(nsError.domain), code=\(nsError.code)")
    #endif

    return diagnostics
  }
}
