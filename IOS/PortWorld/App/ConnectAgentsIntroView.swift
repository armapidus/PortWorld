import SwiftUI

struct ConnectAgentsIntroView: View {
  let onContinue: () -> Void

  var body: some View {
    PWOnboardingScaffold(
      style: .centeredHero,
      title: "Connect your agents",
      subtitle: "PortWorld runs against your own backend. Next, you’ll add its URL and optional bearer token.",
      content: {
        EmptyView()
      },
      footer: {
        PWOnboardingButton(title: "Set up backend", action: onContinue)
      }
    )
  }
}
