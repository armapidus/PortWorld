// Root shell for the phone-first assistant with secondary access to future hardware setup.
import SwiftUI

struct MainAppView: View {
  @StateObject private var appSettingsStore = AppSettingsStore()
  @StateObject private var onboardingStore = OnboardingStore()
  @StateObject private var runtimeViewModel: AssistantRuntimeViewModel
  @ObservedObject private var wearablesRuntimeManager: WearablesRuntimeManager
  @State private var isPresentingFutureHardwareSetup = false
  @State private var route: AppRoute = .splash

  init(wearablesRuntimeManager: WearablesRuntimeManager) {
    self.wearablesRuntimeManager = wearablesRuntimeManager
    _runtimeViewModel = StateObject(
      wrappedValue: AssistantRuntimeViewModel(wearablesRuntimeManager: wearablesRuntimeManager)
    )
  }

  var body: some View {
    ZStack {
      switch route {
      case .splash:
        Color.clear
      case .welcome:
        WelcomeShellView {
          onboardingStore.markWelcomeSeen()
          route = .legacyRuntime
        }
      case .legacyRuntime:
        AssistantRuntimeView(
          viewModel: runtimeViewModel,
          onOpenFutureHardwareSetup: {
            isPresentingFutureHardwareSetup = true
          }
        )
      }

      if route == .splash {
        StartupLoadingView()
          .transition(.opacity)
      }
    }
    .animation(.easeOut(duration: 0.24), value: route)
    .sheet(isPresented: $isPresentingFutureHardwareSetup) {
      FutureHardwareSetupView(wearablesRuntimeManager: wearablesRuntimeManager)
    }
    .onAppear {
      let _ = appSettingsStore
      resolveRoute(for: wearablesRuntimeManager.configurationState)
    }
    .onChange(of: wearablesRuntimeManager.configurationState) { _, newValue in
      resolveRoute(for: newValue)
    }
    .onChange(of: onboardingStore.progress) { _, _ in
      guard route != .splash else { return }
      route = onboardingStore.shouldShowWelcome ? .welcome : .legacyRuntime
    }
  }
}

private extension MainAppView {
  func resolveRoute(
    for configurationState: WearablesRuntimeManager.ConfigurationState
  ) {
    switch configurationState {
    case .idle, .configuring:
      route = .splash
    case .ready, .failed:
      route = onboardingStore.shouldShowWelcome ? .welcome : .legacyRuntime
    }
  }
}
