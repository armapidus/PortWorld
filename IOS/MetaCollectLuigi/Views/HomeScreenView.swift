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

  var body: some View {
    ZStack {
      Color.white.edgesIgnoringSafeArea(.all)

      VStack(spacing: 12) {
        Spacer()

        Image(.cameraAccessIcon)
          .resizable()
          .aspectRatio(contentMode: .fit)
          .frame(width: 120)

        VStack(spacing: 12) {
          TipRowView(
            resource: .smartGlassesIcon,
            title: "Video Capture",
            text: "Record videos directly from your glasses, from your point of view.",
            iconColor: .black,
            titleColor: .black,
            textColor: .gray
          )
          TipRowView(
            resource: .soundIcon,
            title: "Open-Ear Audio",
            text: "Hear notifications while keeping your ears open to the world around you.",
            iconColor: .black,
            titleColor: .black,
            textColor: .gray
          )
          TipRowView(
            resource: .walkingIcon,
            title: "Enjoy On-the-Go",
            text: "Stay hands-free while you move through your day. Move freely, stay connected.",
            iconColor: .black,
            titleColor: .black,
            textColor: .gray
          )
        }

        Spacer()

        VStack(spacing: 20) {
          Text("You'll be redirected to the Meta AI app to confirm your connection.")
            .font(.system(size: 14))
            .foregroundColor(.gray)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 12)

          CustomButton(
            title: viewModel.registrationState == .registering ? "Connecting..." : "Connect my glasses",
            style: .primary,
            isDisabled: viewModel.registrationState == .registering
          ) {
            viewModel.connectGlasses()
          }
        }
      }
      .padding(.all, 24)
    }
  }

}
