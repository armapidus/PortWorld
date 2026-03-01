/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the license found in the
 * LICENSE file in the root directory of this source tree.
 */

//
// HomeScreenView.swift
//
// Welcome screen that guides users through the DAT SDK registration process.
// This view is displayed when the app is not yet registered.
//

import MWDATCore
import SwiftUI

struct HomeScreenView: View {
  @ObservedObject var viewModel: WearablesViewModel
  @State private var isRunningExampleTest = false
  @State private var exampleTestStateText = "idle"
  @State private var exampleTestDetailText = "Backend test not started yet."
  @State private var exampleTester = ExampleMediaPipelineTester(runtimeConfig: RuntimeConfig.load())

  var body: some View {
    ZStack {
      LinearGradient(
        colors: [Color(red: 0.96, green: 0.97, blue: 1), Color(red: 0.95, green: 0.95, blue: 0.94)],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
      )
      .ignoresSafeArea()

      ScrollView(showsIndicators: false) {
        VStack(alignment: .leading, spacing: 18) {
          VStack(alignment: .leading, spacing: 8) {
            Text("PortWorld")
              .font(.system(.largeTitle, design: .rounded).weight(.bold))
              .foregroundColor(.black.opacity(0.85))

            Text("Hands-free multimodal assistant for smart glasses")
              .font(.system(.headline, design: .rounded).weight(.medium))
              .foregroundColor(.black.opacity(0.58))
          }
          .padding(.top, 8)

          HStack(spacing: 14) {
            Image(.cameraAccessIcon)
              .resizable()
              .aspectRatio(contentMode: .fit)
              .frame(width: 70, height: 70)
              .padding(12)
              .background(Color.appPrimary.opacity(0.12))
              .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))

            VStack(alignment: .leading, spacing: 6) {
              Text("Connect your glasses")
                .font(.system(.title3, design: .rounded).weight(.semibold))
                .foregroundColor(.black.opacity(0.85))
              Text("Authorize once in Meta AI app, then run live voice + vision flows.")
                .font(.system(.subheadline, design: .rounded).weight(.medium))
                .foregroundColor(.black.opacity(0.62))
            }
          }
          .padding(16)
          .frame(maxWidth: .infinity, alignment: .leading)
          .background(Color.white.opacity(0.9))
          .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
              .stroke(Color.black.opacity(0.06), lineWidth: 1)
          )
          .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))

          VStack(spacing: 10) {
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
        .padding(.horizontal, 20)
        .padding(.top, 16)
        .padding(.bottom, 140)
      }
    }
    .safeAreaInset(edge: .bottom) {
      VStack(spacing: 10) {
        Text("You will be redirected to the Meta AI app to confirm access.")
          .font(.system(.caption, design: .rounded).weight(.medium))
          .foregroundColor(.black.opacity(0.6))
          .multilineTextAlignment(.leading)
          .frame(maxWidth: .infinity, alignment: .leading)

        Button {
          viewModel.connectGlasses()
        } label: {
          HStack(spacing: 10) {
            Image(systemName: viewModel.registrationState == .registering ? "hourglass" : "bolt.horizontal.fill")
            Text(viewModel.registrationState == .registering ? "Connecting..." : "Connect my glasses")
          }
          .font(.system(.headline, design: .rounded).weight(.semibold))
          .foregroundColor(.white)
          .frame(maxWidth: .infinity)
          .frame(height: 54)
        }
        .buttonStyle(.plain)
        .background(viewModel.registrationState == .registering ? Color.gray.opacity(0.5) : Color.appPrimary)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .disabled(viewModel.registrationState == .registering)

        Button {
          Task {
            await runHomeExampleMediaPipelineTest()
          }
        } label: {
          HStack(spacing: 10) {
            Image(systemName: isRunningExampleTest ? "hourglass" : "sparkles")
            Text(isRunningExampleTest ? "Running backend test..." : "TEST BACKEND (Example Media)")
          }
          .font(.system(.subheadline, design: .rounded).weight(.semibold))
          .foregroundColor(.black.opacity(0.85))
          .frame(maxWidth: .infinity)
          .frame(height: 46)
        }
        .buttonStyle(.plain)
        .background(Color.white)
        .overlay(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .stroke(Color.black.opacity(0.15), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .disabled(isRunningExampleTest)

        Text("Backend test: \(exampleTestStateText) - \(exampleTestDetailText)")
          .font(.system(.caption2, design: .rounded).weight(.medium))
          .foregroundColor(.black.opacity(0.62))
          .lineLimit(2)
          .frame(maxWidth: .infinity, alignment: .leading)
      }
      .padding(.horizontal, 16)
      .padding(.top, 12)
      .padding(.bottom, 12)
      .background(Color.white.opacity(0.92))
      .overlay(alignment: .top) {
        Divider()
      }
    }
  }

  @MainActor
  private func runHomeExampleMediaPipelineTest() async {
    guard !isRunningExampleTest else { return }

    isRunningExampleTest = true
    exampleTestStateText = "sending"
    exampleTestDetailText = "Uploading example image, audio, and video..."

    do {
      let result = try await exampleTester.runExamplePipeline()
      exampleTestStateText = "done"
      exampleTestDetailText = "HTTP \(result.statusCode), \(result.responseBytes) bytes, playback \(max(0, result.playbackDurationMs)) ms"
    } catch {
      exampleTestStateText = "failed"
      exampleTestDetailText = error.localizedDescription
    }

    isRunningExampleTest = false
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
        .foregroundColor(.black.opacity(0.85))
        .aspectRatio(contentMode: .fit)
        .frame(width: 20, height: 20)
        .padding(10)
        .background(Color.white.opacity(0.8))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))

      VStack(alignment: .leading, spacing: 3) {
        Text(title)
          .font(.system(.subheadline, design: .rounded).weight(.semibold))
          .foregroundColor(.black.opacity(0.85))
        Text(detail)
          .font(.system(.caption, design: .rounded).weight(.medium))
          .foregroundColor(.black.opacity(0.58))
      }
      Spacer()
    }
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Color.white.opacity(0.75))
    .overlay(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .stroke(Color.black.opacity(0.06), lineWidth: 1)
    )
    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
  }
}
