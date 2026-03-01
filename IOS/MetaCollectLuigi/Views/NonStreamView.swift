/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the license found in the
 * LICENSE file in the root directory of this source tree.
 */

//
// NonStreamView.swift
//
// Default screen to show getting started tips after app connection
// Initiates runtime activation
//

import MWDATCore
import SwiftUI

struct NonStreamView: View {
  @ObservedObject var viewModel: StreamSessionViewModel
  @ObservedObject var wearablesVM: WearablesViewModel
  @State private var sheetHeight: CGFloat = 300

  var body: some View {
    ZStack {
      Color.black.edgesIgnoringSafeArea(.all)

      VStack {
        HStack {
          Spacer()
          Menu {
            Button("Disconnect", role: .destructive) {
              wearablesVM.disconnectGlasses()
            }
            .disabled(wearablesVM.registrationState != .registered)
          } label: {
            Image(systemName: "gearshape")
              .resizable()
              .aspectRatio(contentMode: .fit)
              .foregroundColor(.white)
              .frame(width: 24, height: 24)
          }
        }

        Spacer()

        VStack(spacing: 12) {
          Image(.cameraAccessIcon)
            .resizable()
            .renderingMode(.template)
            .foregroundColor(.white)
            .aspectRatio(contentMode: .fit)
            .frame(width: 120)

          Text("Activate Assistant Runtime")
            .font(.system(size: 20, weight: .semibold))
            .foregroundColor(.white)

          Text("One tap starts session streaming, rolling capture hooks, and runtime telemetry. On-device wake is preferred; manual wake remains available as fallback.")
            .font(.system(size: 15))
            .multilineTextAlignment(.center)
            .foregroundColor(.white)
        }
        .padding(.horizontal, 12)

        Spacer()

        HStack(spacing: 8) {
          Image(systemName: "hourglass")
            .resizable()
            .aspectRatio(contentMode: .fit)
            .foregroundColor(.white.opacity(0.7))
            .frame(width: 16, height: 16)

          Text("Waiting for an active device")
            .font(.system(size: 14))
            .foregroundColor(.white.opacity(0.7))
        }
        .padding(.bottom, 12)
        .opacity(viewModel.hasActiveDevice ? 0 : 1)

        CustomButton(
          title: activateButtonTitle,
          style: .primary,
          isDisabled: !viewModel.canActivateAssistantRuntime
        ) {
          Task {
            await viewModel.activateAssistantRuntime()
          }
        }

        RuntimeStatusPanelView(viewModel: viewModel)
          .padding(.top, 12)
      }
      .padding(.all, 24)
    }
    .sheet(isPresented: $wearablesVM.showGettingStartedSheet) {
      if #available(iOS 16.0, *) {
        GettingStartedSheetView(height: $sheetHeight)
          .presentationDetents([.height(sheetHeight)])
          .presentationDragIndicator(.visible)
      } else {
        GettingStartedSheetView(height: $sheetHeight)
      }
    }
    .task {
      await viewModel.preflightWakeAuthorization()
    }
  }

  private var activateButtonTitle: String {
    switch viewModel.assistantRuntimeState {
    case .activating:
      return "Activating..."
    case .failed:
      return "Retry activation"
    default:
      return "Activate assistant"
    }
  }
}

private struct RuntimeStatusPanelView: View {
  @ObservedObject var viewModel: StreamSessionViewModel

  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      Text("Runtime Status")
        .font(.system(size: 16, weight: .semibold))
        .foregroundColor(.white)

      Text("Session: \(viewModel.runtimeSessionStateText)")
      Text("Wake: \(viewModel.runtimeWakeStateText)  Count: \(viewModel.runtimeWakeCount)")
      Text("Wake Engine: \(viewModel.runtimeWakeEngineText)")
      Text("Wake Runtime: \(viewModel.runtimeWakeRuntimeText)")
      Text("Speech Auth: \(viewModel.runtimeSpeechAuthorizationText)")
      Text("Manual Fallback: \(viewModel.runtimeManualWakeFallbackText)")
      Text("Query: \(viewModel.runtimeQueryStateText)  Count: \(viewModel.runtimeQueryCount)")
      Text("Photo: \(viewModel.runtimePhotoStateText)  Uploaded: \(viewModel.runtimePhotoUploadCount)")
      Text("Playback: \(viewModel.runtimePlaybackStateText)  Chunks: \(viewModel.runtimePlaybackChunkCount)")
      Text("Backend: \(viewModel.runtimeBackendText)")
        .lineLimit(2)
      Text("Session ID: \(viewModel.runtimeSessionIdText)")
      Text("Query ID: \(viewModel.runtimeQueryIdText)")
      Text("Video Frames Routed: \(viewModel.runtimeVideoFrameCount)")

      Divider().background(Color.white.opacity(0.2))

      Text("Audio State: \(viewModel.audioStateText)")
      Text("Audio Chunks: \(viewModel.audioChunkCount)  Bytes: \(viewModel.audioByteCount)")
      Text("Audio Session Dir: \(viewModel.audioSessionPath)")
        .lineLimit(2)

      if !viewModel.runtimeErrorText.isEmpty {
        Text("Runtime Error: \(viewModel.runtimeErrorText)")
          .foregroundColor(.red)
      }

      if !viewModel.audioLastError.isEmpty {
        Text("Audio Error: \(viewModel.audioLastError)")
          .foregroundColor(.red)
      }
    }
    .font(.system(size: 12))
    .foregroundColor(.white.opacity(0.9))
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Color.white.opacity(0.08))
    .cornerRadius(12)
  }
}

struct GettingStartedSheetView: View {
  @Environment(\.dismiss) var dismiss
  @Binding var height: CGFloat

  var body: some View {
    VStack(spacing: 24) {
      Text("Getting started")
        .font(.system(size: 18, weight: .semibold))
        .foregroundColor(.primary)

      VStack(spacing: 12) {
        TipRowView(
          resource: .videoIcon,
          text: "First, Camera Access needs permission to use your glasses camera.",
          iconColor: .primary,
          titleColor: .primary,
          textColor: .primary
        )
        TipRowView(
          resource: .tapIcon,
          text: "Capture photos by tapping the camera button.",
          iconColor: .primary,
          titleColor: .primary,
          textColor: .primary
        )
        TipRowView(
          resource: .smartGlassesIcon,
          text: "The capture LED lets others know when you're capturing content or going live.",
          iconColor: .primary,
          titleColor: .primary,
          textColor: .primary
        )
      }
      .padding(.bottom, 16)

      CustomButton(
        title: "Continue",
        style: .primary,
        isDisabled: false
      ) {
        dismiss()
      }
    }
    .padding(.all, 24)
    .background(
      GeometryReader { geo -> Color in
        DispatchQueue.main.async {
          height = geo.size.height
        }
        return Color.clear
      }
    )
  }
}
