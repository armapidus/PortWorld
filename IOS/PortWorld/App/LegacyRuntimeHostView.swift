import SwiftUI

struct LegacyRuntimeHostView: View {
  let wearablesRuntimeManager: WearablesRuntimeManager
  let settings: AppSettingsStore.Settings
  let onOpenFutureHardwareSetup: () -> Void

  @StateObject private var viewModel: AssistantRuntimeViewModel

  init(
    wearablesRuntimeManager: WearablesRuntimeManager,
    settings: AppSettingsStore.Settings,
    onOpenFutureHardwareSetup: @escaping () -> Void
  ) {
    self.wearablesRuntimeManager = wearablesRuntimeManager
    self.settings = settings
    self.onOpenFutureHardwareSetup = onOpenFutureHardwareSetup

    let config = AssistantRuntimeConfig.load(
      backendBaseURLOverride: settings.backendBaseURL,
      bearerTokenOverride: settings.bearerToken
    )
    _viewModel = StateObject(
      wrappedValue: AssistantRuntimeViewModel(
        wearablesRuntimeManager: wearablesRuntimeManager,
        config: config
      )
    )
  }

  var body: some View {
    AssistantRuntimeView(
      viewModel: viewModel,
      onOpenFutureHardwareSetup: onOpenFutureHardwareSetup
    )
  }
}
