/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the license found in the
 * LICENSE file in the root directory of this source tree.
 */

//
// StreamView.swift
//
// Main UI for video streaming from Meta wearable devices using the DAT SDK.
// This view demonstrates the complete streaming API: video streaming with real-time display, photo capture,
// and error handling.
//

import MWDATCore
import SwiftUI

struct StreamView: View {
  @ObservedObject var viewModel: StreamSessionViewModel
  @ObservedObject var wearablesVM: WearablesViewModel

  var body: some View {
    ZStack {
      Color.black
        .edgesIgnoringSafeArea(.all)

      if let videoFrame = viewModel.currentVideoFrame, viewModel.hasReceivedFirstFrame {
        GeometryReader { geometry in
          Image(uiImage: videoFrame)
            .resizable()
            .aspectRatio(contentMode: .fill)
            .frame(width: geometry.size.width, height: geometry.size.height)
            .clipped()
        }
        .edgesIgnoringSafeArea(.all)
      } else {
        ProgressView()
          .scaleEffect(1.5)
          .foregroundColor(.white)
      }

      VStack {
        HStack {
          StreamRuntimeOverlay(viewModel: viewModel)
          Spacer()
        }
        Spacer()
        ControlsView(viewModel: viewModel)
      }
      .padding(.all, 24)
    }
    .onDisappear {
      Task {
        if viewModel.canDeactivateAssistantRuntime {
          await viewModel.deactivateAssistantRuntime()
        }
      }
    }
    .sheet(isPresented: $viewModel.showPhotoPreview) {
      if let photo = viewModel.capturedPhoto {
        PhotoPreviewView(
          photo: photo,
          onDismiss: {
            viewModel.dismissPhotoPreview()
          }
        )
      }
    }
  }
}

private struct StreamRuntimeOverlay: View {
  @ObservedObject var viewModel: StreamSessionViewModel

  var body: some View {
    VStack(alignment: .leading, spacing: 4) {
      Text("Session: \(viewModel.runtimeSessionStateText)")
      Text("Wake: \(viewModel.runtimeWakeStateText)  Query: \(viewModel.runtimeQueryStateText)")
      Text("Photo: \(viewModel.runtimePhotoStateText)  Playback: \(viewModel.runtimePlaybackStateText)")
      Text("Frames: \(viewModel.runtimeVideoFrameCount)  Uploaded: \(viewModel.runtimePhotoUploadCount)")
      Text("Backend: \(viewModel.runtimeBackendText)")
        .lineLimit(1)

      if !viewModel.runtimeErrorText.isEmpty {
        Text("Error: \(viewModel.runtimeErrorText)")
          .foregroundColor(.red)
      }
    }
    .font(.system(size: 12, weight: .medium))
    .foregroundColor(.white)
    .padding(10)
    .background(Color.black.opacity(0.45))
    .cornerRadius(10)
  }
}

struct ControlsView: View {
  @ObservedObject var viewModel: StreamSessionViewModel

  var body: some View {
    HStack(spacing: 8) {
      CustomButton(
        title: "Deactivate assistant",
        style: .destructive,
        isDisabled: !viewModel.canDeactivateAssistantRuntime
      ) {
        Task {
          await viewModel.deactivateAssistantRuntime()
        }
      }

      CircleButton(icon: "camera.fill", text: nil) {
        viewModel.capturePhoto()
      }

      CircleButton(icon: "waveform", text: nil) {
        viewModel.triggerWakeForTesting()
      }
    }
  }
}
