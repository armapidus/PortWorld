// StreamView.swift
//
// Main UI for video streaming from Meta wearable devices using the DAT SDK.
// This view demonstrates the complete streaming API: video streaming with real-time display, photo capture,
// and error handling.

import MWDATCore
import SwiftUI

struct StreamView: View {
  let viewModel: SessionViewModel
  let store: SessionStateStore

  var body: some View {
    ZStack {
      Color.black
        .edgesIgnoringSafeArea(.all)

      if let videoFrame = store.currentVideoFrame, store.hasReceivedFirstFrame {
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
          StreamRuntimeOverlay(store: store)
          Spacer()
        }
        Spacer()
        ControlsView(viewModel: viewModel, store: store)
      }
      .padding(.all, 24)
    }
    .onDisappear {
      Task {
        if store.canDeactivateAssistantRuntime {
          await viewModel.deactivateAssistantRuntime()
        }
      }
    }
    .sheet(isPresented: Binding(
      get: { store.showPhotoPreview },
      set: { store.showPhotoPreview = $0 }
    )) {
      if let photo = store.capturedPhoto {
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
  let store: SessionStateStore

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      StreamTransportBadge(
        sessionStateText: store.runtimeSessionStateText,
        playbackStateText: store.runtimePlaybackStateText,
        transportStatusText: store.transportStatusText
      )

      HStack(spacing: 6) {
        Image(systemName: "bolt.fill")
          .foregroundColor(.appPrimary)
        Text("Session: \(store.runtimeSessionStateText)")
      }

      HStack(spacing: 6) {
        Image(systemName: "timer")
          .foregroundColor(.white.opacity(0.7))
        Text("Stream duration: \(store.streamDurationSeconds)s")
      }

      if !store.isInternetReachable {
        HStack(spacing: 6) {
          Image(systemName: "wifi.slash")
            .foregroundColor(.red.opacity(0.9))
          Text("No internet connection")
            .foregroundColor(.red.opacity(0.9))
        }
      }
      
      HStack(spacing: 6) {
        Image(systemName: "waveform")
          .foregroundColor(.white.opacity(0.7))
        Text("Wake: \(store.runtimeWakeStateText)")
      }
      
      HStack(spacing: 6) {
        Image(systemName: "camera.fill")
          .foregroundColor(.white.opacity(0.7))
        Text("Photo: \(store.runtimePhotoStateText)")
      }

      VStack(alignment: .leading, spacing: 2) {
        if let normalizedWakePhrase {
          Text("Wake phrase: \"\(normalizedWakePhrase)\" starts query capture.")
        } else {
          Text("Wake phrase detection starts query capture.")
        }

        if let normalizedSleepPhrase {
          Text("Sleep phrase: \"\(normalizedSleepPhrase)\" ends the active streaming session.")
        } else {
          Text("Sleep phrase detection ends the active streaming session.")
        }
      }
      .font(.system(.caption2, design: .rounded).weight(.semibold))
      .foregroundColor(.white.opacity(0.82))

      if !store.runtimeInfoText.isEmpty {
        HStack(alignment: .top, spacing: 6) {
          Image(systemName: "info.circle.fill")
          Text(store.runtimeInfoText)
        }
        .foregroundColor(.white.opacity(0.9))
      }

      if !store.runtimeErrorText.isEmpty {
        HStack(alignment: .top, spacing: 6) {
          Image(systemName: "exclamationmark.triangle.fill")
          Text(store.runtimeErrorText)
        }
        .foregroundColor(.red.opacity(0.9))
      }
    }
    .font(.system(.caption, design: .rounded).weight(.semibold))
    .foregroundColor(.white)
    .padding(14)
    .background(.ultraThinMaterial)
    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
  }

  private var normalizedWakePhrase: String? {
    let value = store.runtimeWakePhraseText.trimmingCharacters(in: .whitespacesAndNewlines)
    return value.isEmpty ? nil : value
  }

  private var normalizedSleepPhrase: String? {
    let value = store.runtimeSleepPhraseText.trimmingCharacters(in: .whitespacesAndNewlines)
    return value.isEmpty ? nil : value
  }
}

private struct StreamTransportBadge: View {
  let sessionStateText: String
  let playbackStateText: String
  let transportStatusText: String

  private var badgeColor: Color {
    let state = sessionStateText.lowercased()
    if state == "reconnecting" {
      return Color.orange.opacity(0.22)
    }
    if state == "active" {
      return Color.green.opacity(0.22)
    }
    if state == "failed" {
      return Color.red.opacity(0.22)
    }
    return Color.white.opacity(0.14)
  }

  var body: some View {
    HStack(spacing: 8) {
      Image(systemName: "dot.radiowaves.left.and.right")
      Text(transportStatusText)
      Text("Session \(sessionStateText) | Playback \(playbackStateText)")
        .foregroundColor(.white.opacity(0.78))
        .lineLimit(1)
    }
    .font(.system(.caption2, design: .rounded).weight(.bold))
    .foregroundColor(.white)
    .padding(.horizontal, 8)
    .padding(.vertical, 6)
    .background(badgeColor)
    .overlay(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .stroke(Color.white.opacity(0.2), lineWidth: 1)
    )
    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
  }
}

struct ControlsView: View {
  let viewModel: SessionViewModel
  let store: SessionStateStore

  var body: some View {
    HStack(spacing: 8) {
      CustomButton(
        title: "Deactivate assistant",
        style: .destructive,
        isDisabled: !store.canDeactivateAssistantRuntime
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
