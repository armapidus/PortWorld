// Secondary setup screen that consumes the shared app-scoped wearables manager.
import SwiftUI

struct FutureHardwareSetupView: View {
  @Environment(\.dismiss) private var dismiss
  @ObservedObject private var wearablesRuntimeManager: WearablesRuntimeManager

  init(wearablesRuntimeManager: WearablesRuntimeManager) {
    self.wearablesRuntimeManager = wearablesRuntimeManager
  }

  var body: some View {
    NavigationStack {
      Group {
        switch wearablesRuntimeManager.configurationState {
        case .ready:
          HomeScreenView(wearablesRuntimeManager: wearablesRuntimeManager)

        case .idle, .configuring:
          WearablesInitializationView()

        case .failed:
          RecoverableWearablesInitializationView(
            errorMessage: wearablesRuntimeManager.configurationErrorMessage ?? "Wearables SDK is not initialized yet.",
            diagnostics: wearablesRuntimeManager.configurationDiagnostics,
            isRetrying: wearablesRuntimeManager.configurationState == .configuring,
            onRetry: {
              Task {
                await wearablesRuntimeManager.retryConfiguration()
              }
            }
          )
        }
      }
      .navigationTitle("Glasses Setup")
      .navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .cancellationAction) {
          Button("Done") {
            dismiss()
          }
        }
      }
      .task {
        await wearablesRuntimeManager.startIfNeeded()
      }
      .alert("Error", isPresented: Binding(
        get: { wearablesRuntimeManager.showError },
        set: { wearablesRuntimeManager.showError = $0 }
      )) {
        Button("OK") {
          wearablesRuntimeManager.dismissError()
        }
      } message: {
        Text(wearablesRuntimeManager.errorMessage)
      }
    }
  }
}

private struct WearablesInitializationView: View {
  var body: some View {
    PWScreen {
      PWCard(isRaised: true, padding: PWSpace.xl) {
        VStack(spacing: PWSpace.lg) {
          ProgressView()
            .progressViewStyle(.circular)
            .tint(PWColor.textPrimary)
          Text("Initializing Wearables SDK")
            .font(PWTypography.title)
            .foregroundColor(PWColor.textPrimary)
          Text("Preparing the shared glasses capability layer for this app.")
            .font(PWTypography.subbody)
            .foregroundColor(PWColor.textSecondary)
            .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
      }
    }
  }
}

private struct RecoverableWearablesInitializationView: View {
  let errorMessage: String
  let diagnostics: [String]
  let isRetrying: Bool
  let onRetry: () -> Void

  var body: some View {
    PWScreen {
      PWCard(isRaised: true, padding: PWSpace.xl) {
        VStack(alignment: .leading, spacing: PWSpace.lg) {
          Text("Wearables SDK Initialization Failed")
            .font(PWTypography.title)
            .foregroundColor(PWColor.textPrimary)
          Text(errorMessage)
            .font(PWTypography.subbody)
            .multilineTextAlignment(.leading)
            .foregroundColor(PWColor.textSecondary)
          VStack(alignment: .leading, spacing: PWSpace.sm) {
            ForEach(Array(diagnostics.enumerated()), id: \.offset) { _, diagnostic in
              Text("• \(diagnostic)")
                .font(PWTypography.caption)
                .foregroundColor(PWColor.textSecondary)
            }
          }
          PWSecondaryButton(title: isRetrying ? "Retrying..." : "Retry initialization", isDisabled: isRetrying) {
            onRetry()
          }
        }
      }
    }
  }
}
