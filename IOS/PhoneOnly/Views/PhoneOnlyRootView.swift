import SwiftUI

struct PhoneOnlyRootView: View {
  @StateObject private var viewModel = PhoneAssistantRuntimeViewModel()

  var body: some View {
    PhoneAssistantRuntimeView(viewModel: viewModel)
  }
}
