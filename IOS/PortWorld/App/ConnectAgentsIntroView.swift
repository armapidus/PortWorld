import SwiftUI

struct ConnectAgentsIntroView: View {
  let onContinue: () -> Void

  var body: some View {
    PWScreen {
      VStack(spacing: PWSpace.hero) {
        Spacer(minLength: 0)

        VStack(spacing: PWSpace.lg) {
          Text("Connect your agents")
            .font(PWTypography.display)
            .foregroundColor(PWColor.textPrimary)
            .multilineTextAlignment(.center)

          Text("Link your self-hosted backend to unlock voice, memory, and live glasses workflows.")
            .font(PWTypography.body)
            .foregroundColor(PWColor.textSecondary)
            .multilineTextAlignment(.center)
        }
        .frame(maxWidth: 330)

        PWOnboardingButton(title: "Set up backend", action: onContinue)

        Spacer(minLength: 0)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
  }
}
