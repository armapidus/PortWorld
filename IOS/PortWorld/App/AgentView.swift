import SwiftUI

struct AgentView: View {
  @ObservedObject private var viewModel: AssistantRuntimeViewModel
  @ObservedObject private var appSettingsStore: AppSettingsStore
  @ObservedObject private var wearablesRuntimeManager: WearablesRuntimeManager

  init(
    viewModel: AssistantRuntimeViewModel,
    appSettingsStore: AppSettingsStore,
    wearablesRuntimeManager: WearablesRuntimeManager
  ) {
    self.viewModel = viewModel
    self.appSettingsStore = appSettingsStore
    self.wearablesRuntimeManager = wearablesRuntimeManager
  }

  var body: some View {
    let readiness = HomeReadinessState(
      settings: appSettingsStore.settings,
      runtimeStatus: viewModel.status,
      wearablesRuntimeManager: wearablesRuntimeManager
    )

    PWScreen(title: "Agent", titleAlignment: .center, topPadding: PWSpace.md) {
      VStack(spacing: PWSpace.section) {
        Spacer(minLength: 0)

        routeSelector
          .frame(maxWidth: 320)

        AgentPlaceholderView(isAwake: isAwake)

        VStack(spacing: PWSpace.md) {
          Text(statusLine(readiness: readiness))
            .font(PWTypography.title)
            .foregroundStyle(PWColor.textPrimary)
            .multilineTextAlignment(.center)

          Text(detailLine(readiness: readiness))
            .font(PWTypography.body)
            .foregroundStyle(PWColor.textSecondary)
            .multilineTextAlignment(.center)
        }
        .frame(maxWidth: 320)

        primaryButton(readiness: readiness)
          .frame(maxWidth: .infinity)

        Spacer(minLength: 0)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
  }
}

private extension AgentView {
  var isAwake: Bool {
    switch viewModel.status.assistantRuntimeState {
    case .inactive:
      return false
    case .armedListening, .connectingConversation, .activeConversation, .pausedByHardware, .deactivating:
      return true
    }
  }

  var routeSelector: some View {
    VStack(alignment: .leading, spacing: PWSpace.sm) {
      Text("Assistant route")
        .font(PWTypography.headline)
        .foregroundStyle(PWColor.textPrimary)

      Picker(
        "Assistant route",
        selection: Binding(
          get: { viewModel.status.selectedRoute },
          set: { viewModel.selectRoute($0) }
        )
      ) {
        Text("Phone").tag(AssistantRoute.phone)
        Text("Glasses").tag(AssistantRoute.glasses)
      }
      .pickerStyle(.segmented)
      .disabled(viewModel.status.canChangeRoute == false)
    }
  }

  @ViewBuilder
  func primaryButton(readiness: HomeReadinessState) -> some View {
    if viewModel.status.canDeactivate {
      PWPrimaryButton(title: "Deactivate Assistant") {
        Task {
          await viewModel.deactivateAssistant()
        }
      }
    } else {
      PWPrimaryButton(
        title: viewModel.status.activationButtonTitle,
        isDisabled: readiness.canActivateAssistant == false || viewModel.status.canActivateSelectedRoute == false || isStopping
      ) {
        Task {
          await viewModel.activateAssistant()
        }
      }
    }
  }

  var isStopping: Bool {
    viewModel.status.assistantRuntimeState == .deactivating
  }

  func statusLine(readiness: HomeReadinessState) -> String {
    let runtimeState = viewModel.status.assistantRuntimeState

    switch runtimeState {
    case .inactive:
      if readiness.backendStatus.action == .openBackendSettings {
        return "Backend needs attention"
      }
      if viewModel.status.selectedRoute == .glasses && readiness.canActivateAssistant == false {
        return "Glasses aren’t ready"
      }
      return viewModel.status.selectedRoute == .phone ? "Ready on your phone" : "Ready to wake Mario"

    case .connectingConversation:
      return viewModel.status.selectedRoute == .phone ? "Mario is joining on your phone" : "Mario is joining"

    case .armedListening:
      return "Listening for \"\(viewModel.status.wakePhraseText)\""

    case .activeConversation:
      return viewModel.status.selectedRoute == .phone ? "Mario is awake on your phone" : "Mario is awake"

    case .pausedByHardware:
      return "Mario is waiting for your glasses"

    case .deactivating:
      return "Mario is going back to sleep"
    }
  }

  func detailLine(readiness: HomeReadinessState) -> String {
    let runtimeState = viewModel.status.assistantRuntimeState

    switch runtimeState {
    case .inactive:
      if readiness.backendStatus.action == .openBackendSettings {
        return readiness.backendStatus.detail
      }
      if viewModel.status.selectedRoute == .phone {
        return "Use your iPhone microphone and speaker to test the assistant."
      }
      if readiness.canActivateAssistant == false {
        return readiness.glassesStatus.detail
      }
      return "Mario will start through your connected glasses."

    case .connectingConversation:
      return viewModel.status.selectedRoute == .phone
        ? "Phone route is opening a live backend session."
        : "Glasses route is opening a live backend session."

    case .armedListening:
      return viewModel.status.selectedRoute == .phone
        ? "Mario is listening through your iPhone."
        : "Mario is listening through your glasses."

    case .activeConversation:
      return viewModel.status.selectedRoute == .phone
        ? "Phone route is active."
        : "Glasses route is active."

    case .pausedByHardware:
      return "Reconnect your glasses or deactivate the assistant."

    case .deactivating:
      return "Mario is closing the current session."
    }
  }
}

private struct AgentPlaceholderView: View {
  let isAwake: Bool

  var body: some View {
    ZStack {
      Circle()
        .fill(PWColor.surfaceRaised)
        .frame(width: 220, height: 220)
        .overlay(
          Circle()
            .stroke(isAwake ? PWColor.borderStrong : PWColor.border, lineWidth: 1)
        )

      Image(systemName: isAwake ? "sparkles" : "moon.zzz.fill")
        .font(.system(size: 72, weight: .medium))
        .foregroundStyle(isAwake ? PWColor.textPrimary : PWColor.textSecondary)
    }
    .accessibilityElement(children: .ignore)
    .accessibilityLabel(isAwake ? "Mario is awake" : "Mario is asleep")
  }
}
