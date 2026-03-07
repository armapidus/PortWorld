// MainAppView.swift
//
// Central navigation hub for the active assistant product flow.
// The phone-only runtime is the only primary assistant path.
// Legacy glasses/runtime views remain in the repo but are not part of normal navigation.

import MWDATCore
import SwiftUI

struct MainAppView: View {
  let wearables: WearablesInterface
  @ObservedObject private var viewModel: WearablesViewModel
  @StateObject private var phoneRuntimeViewModel: PhoneAssistantRuntimeViewModel

  init(wearables: WearablesInterface, viewModel: WearablesViewModel) {
    self.wearables = wearables
    self.viewModel = viewModel
    _phoneRuntimeViewModel = StateObject(wrappedValue: PhoneAssistantRuntimeViewModel())
  }

  var body: some View {
    Group {
      if viewModel.isPhoneOnlyModeEnabled {
        PhoneAssistantRuntimeView(
          wearablesVM: viewModel,
          viewModel: phoneRuntimeViewModel
        )
      } else {
        HomeScreenView(viewModel: viewModel)
      }
    }
    .onOpenURL { url in
      Task {
        await viewModel.handleMetaCallback(url: url)
      }
    }
  }
}
