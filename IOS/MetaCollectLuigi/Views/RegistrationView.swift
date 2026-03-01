/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the license found in the
 * LICENSE file in the root directory of this source tree.
 */

//
// RegistrationView.swift
//
// Background view that handles callbacks from the Meta AI mobile app during
// DAT SDK registration and permission flows. This invisible view processes deep links
// that complete the OAuth authorization process initiated by the DAT SDK.
//

import SwiftUI

struct RegistrationView: View {
  @ObservedObject var viewModel: WearablesViewModel

  var body: some View {
    EmptyView()
      .onOpenURL { url in
        Task {
          await viewModel.handleMetaCallback(url: url)
        }
      }
  }
}
