//
//  PortWorldApp.swift
//  PortWorld
//
//  Created by Pierre Haas on 28/02/2026.
//

import Foundation
import MWDATCore
import SwiftUI

@main
struct PortWorldApp: App {
  @State private var sdkInitError: String?
  @State private var sdkInitDiagnostics: [String] = []
  @State private var didAttemptInitialSDKInit = false
  @State private var isRetryingSDKInit = false
  @State private var wearables: WearablesInterface?
  @State private var wearablesViewModel: WearablesViewModel?

  var body: some Scene {
    WindowGroup {
      Group {
        if let wearables, let wearablesViewModel {
          MainAppView(wearables: wearables, viewModel: wearablesViewModel)
            .alert("Error", isPresented: Binding(
              get: { wearablesViewModel.showError },
              set: { wearablesViewModel.showError = $0 }
            )) {
              Button("OK") {
                wearablesViewModel.dismissError()
              }
            } message: {
              Text(wearablesViewModel.errorMessage)
            }
        } else {
          RecoverableSDKInitializationView(
            errorMessage: sdkInitError ?? "Wearables SDK is not initialized yet.",
            diagnostics: sdkInitDiagnostics,
            isRetrying: isRetryingSDKInit,
            onRetry: initializeWearablesSDK
          )
        }
      }
      .task {
        guard didAttemptInitialSDKInit == false else { return }
        didAttemptInitialSDKInit = true
        initializeWearablesSDK()
      }
    }
  }

  @MainActor
  private func initializeWearablesSDK() {
    guard isRetryingSDKInit == false else { return }
    isRetryingSDKInit = true
    defer { isRetryingSDKInit = false }

    do {
      try Wearables.configure()
      let sharedWearables = Wearables.shared
      wearables = sharedWearables
      wearablesViewModel = WearablesViewModel(wearables: sharedWearables)
      sdkInitError = nil
      sdkInitDiagnostics = []
    } catch {
      wearables = nil
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

private struct RecoverableSDKInitializationView: View {
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
