// HomeScreenView.swift
//
// Welcome screen that guides users through the DAT SDK registration process.
// This view is displayed when the app is not yet registered.

import MWDATCore
import SwiftUI

struct HomeScreenView: View {
  @Environment(\.dismiss) private var dismiss
  @ObservedObject var wearablesRuntimeManager: WearablesRuntimeManager
  @Namespace private var onboardingAnimation

  private var isRegistering: Bool {
    wearablesRuntimeManager.registrationState == .registering
  }

  private var isRegistered: Bool {
    wearablesRuntimeManager.registrationState == .registered
  }

  private var hasDiscoveredDevice: Bool {
    !wearablesRuntimeManager.devices.isEmpty
  }

  private var registrationStatusTitle: String {
    if isRegistered { return "Connected" }
    if isRegistering { return "Connecting..." }
    return "Not connected"
  }

  private var registrationStatusSubtitle: String {
    if isRegistered { return "Meta hardware features are available, and the main runtime can now choose live glasses audio or the mock-friendly fallback path." }
    if isRegistering {
      return "Waiting for Meta AI confirmation."
    }
    return "Connect glasses for DAT features, or continue with the phone route now."
  }

  var body: some View {
    PWScreen {
      ScrollView(showsIndicators: false) {
        VStack(alignment: .leading, spacing: PWSpace.lg) {
          VStack(alignment: .leading, spacing: PWSpace.sm) {
            Text("PortWorld")
              .font(PWTypography.display)
              .foregroundColor(PWColor.textPrimary)

            Text("Hands-free multimodal assistant for smart glasses")
              .font(PWTypography.subbody)
              .foregroundColor(PWColor.textSecondary)
          }
          .padding(.top, 10)

          HomeGlassCard {
            HStack(alignment: .top, spacing: 12) {
              Image(.cameraAccessIcon)
                .resizable()
                .renderingMode(.template)
                .foregroundColor(PWColor.textPrimary)
                .aspectRatio(contentMode: .fit)
                .frame(width: 46, height: 46)
                .padding(8)
                .background(PWColor.surfaceRaised)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

              VStack(alignment: .leading, spacing: 6) {
                Text(registrationStatusTitle)
                  .font(PWTypography.title)
                  .foregroundColor(PWColor.textPrimary)
                Text(registrationStatusSubtitle)
                  .font(PWTypography.subbody)
                  .foregroundColor(PWColor.textSecondary)
              }

              Spacer(minLength: 0)

              HomeStateBadge(
                text: registrationStatusTitle,
                state: statusBadgeState
              )
            }
          }

          HomeGlassCard {
            VStack(alignment: .leading, spacing: PWSpace.sm) {
              Text("Onboarding progress")
                .font(PWTypography.headline)
                .foregroundColor(PWColor.textPrimary)

              ForEach(progressRows) { row in
                HomeProgressRow(row: row)
                  .matchedGeometryEffect(id: row.id, in: onboardingAnimation)
              }
            }
          }

          HomeGlassCard {
            VStack(alignment: .leading, spacing: PWSpace.sm) {
              Text("Development readiness")
                .font(PWTypography.headline)
                .foregroundColor(PWColor.textPrimary)

              HomeProgressRow(
                row: .init(
                  id: "mock-workflow",
                  title: "Mock workflow",
                  detail: wearablesRuntimeManager.mockWorkflowDetail,
                  status: mockWorkflowStatus
                )
              )

              HomeProgressRow(
                row: .init(
                  id: "hfp-route",
                  title: "Bluetooth HFP route",
                  detail: wearablesRuntimeManager.isHFPRouteAvailable ? "Bidirectional HFP is available on this phone" : "Bidirectional HFP is not detected on this phone right now",
                  status: wearablesRuntimeManager.isHFPRouteAvailable ? .done : .pending
                )
              )

              HomeProgressRow(
                row: .init(
                  id: "audio-mode",
                  title: "Current glasses audio mode",
                  detail: glassesAudioModeDetail,
                  status: glassesAudioStatus
                )
              )

              Text(wearablesRuntimeManager.glassesDevelopmentReadinessDetail)
                .font(PWTypography.caption)
                .foregroundColor(PWColor.textSecondary)
            }
          }

          HomeGlassCard {
            VStack(alignment: .leading, spacing: PWSpace.sm) {
              Text("What you unlock")
                .font(PWTypography.headline)
                .foregroundColor(PWColor.textPrimary)

              HomeFeatureRow(
                resource: .smartGlassesIcon,
                title: "First-person video context",
                detail: "Stream visual context from glasses to your assistant pipeline."
              )
              HomeFeatureRow(
                resource: .soundIcon,
                title: "Voice interaction loop",
                detail: "Capture speech and receive generated audio replies in real time."
              )
              HomeFeatureRow(
                resource: .walkingIcon,
                title: "Field-ready workflow",
                detail: "Designed for hands-busy scenarios: support, repair, and tours."
              )
            }
          }
        }
        .padding(.bottom, 140)
      }
    }
    .animation(.spring(response: 0.35, dampingFraction: 0.85), value: wearablesRuntimeManager.registrationState)
    .animation(.spring(response: 0.35, dampingFraction: 0.85), value: wearablesRuntimeManager.devices.count)
    .safeAreaInset(edge: .bottom) {
      VStack(spacing: 10) {
        if let compatibilityMessage = wearablesRuntimeManager.activeCompatibilityMessage {
          Text(compatibilityMessage)
            .font(PWTypography.caption)
            .foregroundColor(PWColor.warning)
            .multilineTextAlignment(.leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }

        Text(wearablesRuntimeManager.glassesDevelopmentReadinessDetail)
          .font(PWTypography.caption)
          .foregroundColor(PWColor.textSecondary)
          .multilineTextAlignment(.leading)
          .frame(maxWidth: .infinity, alignment: .leading)

        PWSecondaryButton(title: "Back to iPhone Assistant") {
          dismiss()
        }

        #if DEBUG
          PWSecondaryButton(
            title: mockButtonTitle,
            isDisabled: wearablesRuntimeManager.isPreparingMockDevice
          ) {
            Task {
              await wearablesRuntimeManager.toggleMockMode()
            }
          }

          Text("DEBUG: Pair a simulated glasses device for DAT development. Meta registration is still required before the glasses runtime can activate.")
            .font(PWTypography.caption)
            .foregroundColor(PWColor.textSecondary)
            .frame(maxWidth: .infinity, alignment: .leading)
        #endif

        PWPrimaryButton(title: isRegistering ? "Connecting..." : "Connect my glasses", isDisabled: isRegistering) {
          wearablesRuntimeManager.connectGlasses()
        }
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
  }
}

private extension HomeScreenView {
  #if DEBUG
    var mockButtonTitle: String {
      if wearablesRuntimeManager.isPreparingMockDevice { return "Preparing Mock Device…" }
      if wearablesRuntimeManager.isMockModeEnabled { return "Disable Mock Device" }
      return "Use iPhone Mock Device"
    }
  #endif

  var statusBadgeState: HomeStateBadge.State {
    if isRegistered { return .success }
    if isRegistering { return .active }
    return .inactive
  }

  var glassesAudioModeDetail: String {
    switch wearablesRuntimeManager.glassesAudioMode {
    case .inactive:
      return "Inactive"
    case .phone:
      return "Phone audio"
    case .glassesHFP:
      return "Live HFP audio"
    case .glassesMockFallback:
      return "Phone fallback for mock development"
    }
  }

  var glassesAudioStatus: HomeProgressRow.RowData.Status {
    switch wearablesRuntimeManager.glassesAudioMode {
    case .glassesHFP:
      return .done
    case .glassesMockFallback:
      return .active
    case .inactive, .phone:
      return .pending
    }
  }

  var mockWorkflowStatus: HomeProgressRow.RowData.Status {
    switch wearablesRuntimeManager.mockWorkflowState {
    case .ready:
      return .done
    case .preparing:
      return .active
    case .disabled, .failed:
      return .pending
    }
  }

  var progressRows: [HomeProgressRow.RowData] {
    [
      HomeProgressRow.RowData(
        id: "registration",
        title: "Meta app authorization",
        detail: isRegistered ? "Completed" : (isRegistering ? "In progress..." : "Required"),
        status: isRegistered ? .done : (isRegistering ? .active : .pending)
      ),
      HomeProgressRow.RowData(
        id: "device",
        title: "Device discovery",
        detail: hasDiscoveredDevice ? "\(wearablesRuntimeManager.devices.count) device(s) available" : "Waiting for glasses",
        status: hasDiscoveredDevice ? .done : (isRegistered ? .active : .pending)
      ),
      HomeProgressRow.RowData(
        id: "runtime",
        title: "Runtime activation",
        detail: "Phone route available now",
        status: .done
      ),
    ]
  }
}

private struct HomeGlassCard<Content: View>: View {
  @ViewBuilder var content: Content

  var body: some View {
    PWCard(isRaised: true) {
      content
    }
  }
}

private struct HomeStateBadge: View {
  enum State {
    case success
    case active
    case inactive
  }

  let text: String
  let state: State

  private var icon: String {
    switch state {
    case .success:
      return "checkmark.circle.fill"
    case .active:
      return "hourglass.circle.fill"
    case .inactive:
      return "xmark.circle.fill"
    }
  }

  private var tint: Color {
    switch state {
    case .success:
      return PWColor.success
    case .active:
      return PWColor.warning
    case .inactive:
      return PWColor.textSecondary
    }
  }

  var body: some View {
    HStack(spacing: 6) {
      Image(systemName: icon)
      Text(text.uppercased())
        .lineLimit(1)
    }
    .font(PWTypography.caption)
    .foregroundColor(tint)
    .padding(.horizontal, 10)
    .padding(.vertical, 7)
    .background(PWColor.surfaceRaised)
    .clipShape(Capsule())
  }
}

private struct HomeProgressRow: View {
  struct RowData: Identifiable {
    enum Status {
      case done
      case active
      case pending
    }

    let id: String
    let title: String
    let detail: String
    let status: Status
  }

  let row: RowData

  private var icon: String {
    switch row.status {
    case .done:
      return "checkmark.circle.fill"
    case .active:
      return "circle.lefthalf.filled"
    case .pending:
      return "circle"
    }
  }

  private var tint: Color {
    switch row.status {
    case .done:
      return PWColor.success
    case .active:
      return PWColor.warning
    case .pending:
      return PWColor.textSecondary
    }
  }

  var body: some View {
    HStack(alignment: .top, spacing: 10) {
      Image(systemName: icon)
        .font(.system(size: 15, weight: .semibold))
        .foregroundColor(tint)
        .frame(width: 20, alignment: .center)

      VStack(alignment: .leading, spacing: 2) {
        Text(row.title)
          .font(PWTypography.headline)
          .foregroundColor(PWColor.textPrimary)

        Text(row.detail)
          .font(PWTypography.caption)
          .foregroundColor(PWColor.textSecondary)
      }
    }
  }
}

private struct HomeFeatureRow: View {
  let resource: ImageResource
  let title: String
  let detail: String

  var body: some View {
    HStack(alignment: .top, spacing: 12) {
      Image(resource)
        .resizable()
        .renderingMode(.template)
        .foregroundColor(PWColor.textPrimary)
        .aspectRatio(contentMode: .fit)
        .frame(width: 20, height: 20)
        .padding(10)
        .background(PWColor.surfaceRaised)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))

      VStack(alignment: .leading, spacing: 3) {
        Text(title)
          .font(PWTypography.headline)
          .foregroundColor(PWColor.textPrimary)
        Text(detail)
          .font(PWTypography.caption)
          .foregroundColor(PWColor.textSecondary)
      }
      Spacer()
    }
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(PWColor.surface)
    .overlay(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .stroke(PWColor.border, lineWidth: 1)
    )
    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
  }
}
