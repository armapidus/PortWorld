import SwiftUI

private enum AppTab: Hashable {
  case home
  case agent
  case settings
}

enum SettingsScrollTarget: Hashable {
  case backend
  case glasses
  case help
}

struct PostOnboardingShellView: View {
  @ObservedObject var appSettingsStore: AppSettingsStore
  let wearablesRuntimeManager: WearablesRuntimeManager
  let shouldShowProfileSetupCallToAction: Bool
  let onOpenMetaSetup: () -> Void
  let onOpenProfileSetup: () -> Void

  @StateObject private var viewModel: AssistantRuntimeViewModel
  @State private var selectedTab: AppTab = .home
  @State private var settingsScrollTarget: SettingsScrollTarget?

  init(
    appSettingsStore: AppSettingsStore,
    wearablesRuntimeManager: WearablesRuntimeManager,
    shouldShowProfileSetupCallToAction: Bool,
    onOpenMetaSetup: @escaping () -> Void,
    onOpenProfileSetup: @escaping () -> Void
  ) {
    self.appSettingsStore = appSettingsStore
    self.wearablesRuntimeManager = wearablesRuntimeManager
    self.shouldShowProfileSetupCallToAction = shouldShowProfileSetupCallToAction
    self.onOpenMetaSetup = onOpenMetaSetup
    self.onOpenProfileSetup = onOpenProfileSetup

    let config = AssistantRuntimeConfig.load(
      backendBaseURLOverride: appSettingsStore.settings.backendBaseURL,
      bearerTokenOverride: appSettingsStore.settings.bearerToken
    )
    _viewModel = StateObject(
      wrappedValue: AssistantRuntimeViewModel(
        appSettingsStore: appSettingsStore,
        wearablesRuntimeManager: wearablesRuntimeManager,
        config: config
      )
    )
  }

  var body: some View {
    TabView(selection: $selectedTab) {
      HomeView(
        viewModel: viewModel,
        appSettingsStore: appSettingsStore,
        wearablesRuntimeManager: wearablesRuntimeManager,
        shouldShowProfileSetupCallToAction: shouldShowProfileSetupCallToAction,
        onOpenBackendSettings: {
          openSettings(.backend)
        },
        onOpenGlassesSettings: {
          openSettings(.glasses)
        },
        onOpenProfileSetup: onOpenProfileSetup
      )
      .tabItem {
        Label("Home", systemImage: "house")
      }
      .tag(AppTab.home)

      AgentView(
        viewModel: viewModel,
        appSettingsStore: appSettingsStore,
        wearablesRuntimeManager: wearablesRuntimeManager
      )
      .tabItem {
        Label("Agent", systemImage: "sparkles")
      }
      .tag(AppTab.agent)

      SettingsView(
        appSettingsStore: appSettingsStore,
        viewModel: viewModel,
        wearablesRuntimeManager: wearablesRuntimeManager,
        scrollTarget: $settingsScrollTarget,
        shouldShowProfileSetupCallToAction: shouldShowProfileSetupCallToAction,
        onOpenMetaSetup: onOpenMetaSetup,
        onOpenProfileSetup: onOpenProfileSetup
      )
      .tabItem {
        Label("Settings", systemImage: "gearshape")
      }
      .tag(AppTab.settings)
    }
    .tint(PWColor.textPrimary)
    .toolbarBackground(PWColor.background, for: .tabBar)
    .toolbarBackground(.visible, for: .tabBar)
  }
}

private extension PostOnboardingShellView {
  func openSettings(_ target: SettingsScrollTarget) {
    settingsScrollTarget = target
    selectedTab = .settings
  }
}
