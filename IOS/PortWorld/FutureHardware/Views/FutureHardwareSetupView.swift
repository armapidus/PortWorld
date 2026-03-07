// Secondary setup screen that lazily initializes wearables/DAT only when requested.
import Combine
import Foundation
import MWDATCore
import SwiftUI

@MainActor
final class FutureHardwareSetupModel: ObservableObject {
  @Published var sdkInitError: String?
  @Published var sdkInitDiagnostics: [String] = []
  @Published var didAttemptInitialSDKInit = false
  @Published var isRetryingSDKInit = false
  @Published var wearablesViewModel: WearablesViewModel?

  func initializeWearablesSDKIfNeeded() {
    guard didAttemptInitialSDKInit == false else { return }
    didAttemptInitialSDKInit = true
    initializeWearablesSDK()
  }

  func initializeWearablesSDK() {
    guard isRetryingSDKInit == false else { return }
    isRetryingSDKInit = true
    defer { isRetryingSDKInit = false }

    do {
      // The DAT SDK should be configured only once per app lifetime.
      try Wearables.configure()
      wearablesViewModel = WearablesViewModel(wearables: Wearables.shared)
      sdkInitError = nil
      sdkInitDiagnostics = []
    } catch {
      wearablesViewModel = nil
      sdkInitError = error.localizedDescription
      sdkInitDiagnostics = Self.buildInitializationDiagnostics(from: error)
    }
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

struct FutureHardwareSetupView: View {
  @Environment(\.dismiss) private var dismiss
  @ObservedObject private var model: FutureHardwareSetupModel

  init(model: FutureHardwareSetupModel) {
    self.model = model
  }

  var body: some View {
    NavigationStack {
      Group {
        if let wearablesViewModel = model.wearablesViewModel {
          HomeScreenView(viewModel: wearablesViewModel)
        } else {
          RecoverableWearablesInitializationView(
            errorMessage: model.sdkInitError ?? "Wearables SDK is not initialized yet.",
            diagnostics: model.sdkInitDiagnostics,
            isRetrying: model.isRetryingSDKInit,
            onRetry: model.initializeWearablesSDK
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
        model.initializeWearablesSDKIfNeeded()
      }
      .onOpenURL { url in
        Task {
          await model.wearablesViewModel?.handleMetaCallback(url: url)
        }
      }
      .alert("Error", isPresented: Binding(
        get: { model.wearablesViewModel?.showError ?? false },
        set: { newValue in
          model.wearablesViewModel?.showError = newValue
        }
      )) {
        Button("OK") {
          model.wearablesViewModel?.dismissError()
        }
      } message: {
        Text(model.wearablesViewModel?.errorMessage ?? "")
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
    VStack(alignment: .leading, spacing: 16) {
      Text("Wearables SDK Initialization Failed")
        .font(.headline)
      Text(errorMessage)
        .font(.subheadline)
        .multilineTextAlignment(.leading)
        .foregroundColor(.secondary)
      VStack(alignment: .leading, spacing: 8) {
        ForEach(Array(diagnostics.enumerated()), id: \.offset) { _, diagnostic in
          Text("• \(diagnostic)")
            .font(.footnote)
            .foregroundColor(.secondary)
        }
      }
      Button(isRetrying ? "Retrying..." : "Retry initialization") {
        onRetry()
      }
      .disabled(isRetrying)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
    .padding(24)
  }
}
