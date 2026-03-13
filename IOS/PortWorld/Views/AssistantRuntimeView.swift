// Primary runtime screen for the assistant runtime across phone and glasses routes.
import SwiftUI

struct AssistantRuntimeView: View {
  @ObservedObject private var viewModel: AssistantRuntimeViewModel
  private let onOpenFutureHardwareSetup: () -> Void
  @Environment(\.scenePhase) private var scenePhase

  init(
    viewModel: AssistantRuntimeViewModel,
    onOpenFutureHardwareSetup: @escaping () -> Void
  ) {
    self.viewModel = viewModel
    self.onOpenFutureHardwareSetup = onOpenFutureHardwareSetup
  }

  var body: some View {
    let status = viewModel.status

    PWScreen {
      ScrollView(showsIndicators: false) {
        VStack(alignment: .leading, spacing: PWSpace.section) {
          VStack(alignment: .leading, spacing: 8) {
            Text("Assistant Runtime")
              .font(PWTypography.display)
              .foregroundColor(PWColor.textPrimary)

            Text("Primary assistant runtime. Phone mode remains stable, and the glasses route now activates through DAT lifecycle with live HFP audio when available, or a labeled phone fallback while developing with the mock device path.")
              .font(PWTypography.subbody)
              .foregroundColor(PWColor.textSecondary)
          }

          PhoneAssistantPanel(title: "Runtime Route") {
            HStack(spacing: 10) {
              RuntimeRouteButton(
                title: "Phone",
                subtitle: "Live now",
                isSelected: status.selectedRoute == .phone,
                isEnabled: status.canChangeRoute
              ) {
                viewModel.selectRoute(.phone)
              }

              RuntimeRouteButton(
                title: "Glasses",
                subtitle: "DAT + audio aware",
                isSelected: status.selectedRoute == .glasses,
                isEnabled: status.canChangeRoute
              ) {
                viewModel.selectRoute(.glasses)
              }
            }

            HStack(spacing: 8) {
              Circle()
                .fill(glassesReadinessColor(status.glassesReadinessKind))
                .frame(width: 10, height: 10)
              Text(status.glassesReadinessTitle)
                .font(PWTypography.headline)
                .foregroundColor(PWColor.textPrimary)
            }

            Text(status.glassesReadinessDetail)
              .font(PWTypography.caption)
              .foregroundColor(PWColor.textSecondary)

            LabeledContent("Glasses session", value: status.glassesSessionText)
            LabeledContent("Active glasses", value: status.activeGlassesDeviceText)
            LabeledContent("Glasses audio", value: status.glassesAudioModeText)
            LabeledContent("HFP route", value: status.hfpRouteText)
            LabeledContent("Mock workflow", value: status.mockWorkflowText)

            if status.selectedRoute == .phone {
              LabeledContent("Phone vision debug", value: status.debugPhoneVisionModeText)
              Text(status.debugPhoneVisionDetailText)
                .font(PWTypography.caption)
                .foregroundColor(PWColor.textSecondary)
            }

            if status.selectedRoute == .glasses {
              Text(status.glassesDevelopmentDetailText)
                .font(PWTypography.caption)
                .foregroundColor(PWColor.textSecondary)
            }
          }

          PhoneAssistantPanel(title: "Assistant State") {
            LabeledContent("Lifecycle", value: status.assistantRuntimeState.rawValue)
            LabeledContent("Session", value: status.sessionID)
            LabeledContent("Selected route", value: status.selectedRoute.rawValue)
            LabeledContent("Active route", value: status.activeRouteText)
            LabeledContent("Wake phrase", value: status.wakePhraseText)
            LabeledContent("Sleep phrase", value: status.sleepPhraseText)
          }

          PhoneAssistantPanel(title: "Subsystem Status") {
            LabeledContent("Audio mode", value: status.audioModeText)
            LabeledContent("Audio I/O", value: status.audioStatusText)
            LabeledContent("Backend client", value: status.backendStatusText)
            LabeledContent("Transport", value: status.transportStatusText)
            LabeledContent("Uplink", value: status.uplinkStatusText)
            LabeledContent("Playback", value: status.playbackStatusText)
            LabeledContent("Wake detector", value: status.wakeStatusText)
            LabeledContent("Playback route", value: status.playbackRouteText)
            LabeledContent("Vision capture", value: status.visionCaptureStateText)
            LabeledContent("Vision uploads", value: "\(status.visionUploadCount)")
            LabeledContent("Vision failures", value: "\(status.visionUploadFailureCount)")
          }

          PhoneAssistantPanel(title: "Notes") {
            Text(status.infoText.isEmpty ? "No runtime notes." : status.infoText)
              .font(PWTypography.body)
              .foregroundColor(PWColor.textPrimary)
            if !status.visionLastErrorText.isEmpty {
              Text(status.visionLastErrorText)
                .font(PWTypography.caption)
                .foregroundColor(PWColor.warning)
            }
            if !status.errorText.isEmpty {
              Text(status.errorText)
                .font(PWTypography.caption)
                .foregroundColor(PWColor.error)
            }
          }
        }
        .padding(.bottom, 160)
      }
    }
    .safeAreaInset(edge: .bottom) {
      VStack(spacing: PWSpace.sm) {
        if status.assistantRuntimeState == .inactive {
          PWPrimaryButton(
            title: status.activationButtonTitle,
            isDisabled: status.canActivateSelectedRoute == false
          ) {
            Task {
              await viewModel.activateAssistant()
            }
          }
        }

        if status.canDeactivate {
          PWDestructiveButton(title: "Deactivate Assistant") {
            Task {
              await viewModel.deactivateAssistant()
            }
          }
        }

        if status.canEndConversation {
          PWSecondaryButton(title: "End Conversation") {
            Task {
              await viewModel.endConversation()
            }
          }
        }

        PWSecondaryButton(title: "Open Glasses Setup") {
          onOpenFutureHardwareSetup()
        }

        #if DEBUG
          if status.selectedRoute == .phone {
            PWSecondaryButton(
              title: status.debugPhoneVisionToggleTitle,
              isDisabled: status.canToggleDebugPhoneVision == false
            ) {
              viewModel.toggleDebugPhoneVisionMode()
            }
          }
        #endif
      }
      .padding(.horizontal, PWSpace.lg)
      .padding(.top, PWSpace.md)
      .padding(.bottom, PWSpace.md)
      .background(PWColor.background)
      .overlay(alignment: .top) {
        Rectangle()
          .fill(PWColor.borderSubtle)
          .frame(height: 1)
      }
    }
    .onAppear {
      viewModel.handleScenePhaseChange(scenePhase)
    }
    .onChange(of: scenePhase) { _, newPhase in
      viewModel.handleScenePhaseChange(newPhase)
    }
  }
}

private extension AssistantRuntimeView {
  func glassesReadinessColor(_ kind: GlassesReadinessKind) -> Color {
    switch kind {
    case .neutral:
      return PWColor.textSecondary
    case .success:
      return PWColor.success
    case .warning:
      return PWColor.warning
    case .error:
      return PWColor.error
    }
  }
}

private struct PhoneAssistantPanel<Content: View>: View {
  let title: String
  @ViewBuilder let content: Content

  var body: some View {
    PWCard {
      VStack(alignment: .leading, spacing: PWSpace.sm) {
        Text(title)
          .font(PWTypography.headline)
          .foregroundColor(PWColor.textPrimary)

        content
      }
    }
  }
}

private struct RuntimeRouteButton: View {
  let title: String
  let subtitle: String
  let isSelected: Bool
  let isEnabled: Bool
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      VStack(alignment: .leading, spacing: 4) {
        Text(title)
          .font(PWTypography.headline)
          .foregroundColor(isSelected ? PWColor.primaryButtonText : PWColor.textPrimary)
        Text(subtitle)
          .font(PWTypography.caption)
          .foregroundColor(isSelected ? PWColor.primaryButtonText.opacity(0.7) : PWColor.textSecondary)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(.vertical, 12)
      .padding(.horizontal, 14)
      .background(isSelected ? PWColor.primaryButtonFill : PWColor.surfaceRaised)
      .overlay(
        RoundedRectangle(cornerRadius: 14, style: .continuous)
          .stroke(isSelected ? PWColor.primaryButtonFill : PWColor.border, lineWidth: 1)
      )
      .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
    .buttonStyle(.plain)
    .disabled(isEnabled == false)
    .opacity(isEnabled ? 1 : 0.65)
  }
}
