import SwiftUI

struct WelcomeShellView: View {
  let onContinue: () -> Void

  var body: some View {
    PWOnboardingScaffold(
      style: .centeredHero,
      title: "Welcome to PortWorld",
      subtitle: "Your hands-free assistant for Meta smart glasses.",
      content: {
        EmptyView()
      },
      footer: {
        PWOnboardingButton(title: "Continue", action: onContinue)
      }
    )
  }
}
