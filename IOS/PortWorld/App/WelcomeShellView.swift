import SwiftUI

struct WelcomeShellView: View {
  let onContinue: () -> Void

  var body: some View {
    PWScreen {
      VStack(spacing: PWSpace.hero) {
        Spacer(minLength: 0)

        VStack(spacing: PWSpace.lg) {
          Text("Welcome to PortWorld")
            .font(PWTypography.display)
            .foregroundColor(PWColor.textPrimary)
            .multilineTextAlignment(.center)

          Text("Your hands-free assistant for Meta smart glasses.")
            .font(PWTypography.body)
            .foregroundColor(PWColor.textSecondary)
            .multilineTextAlignment(.center)
        }
        .frame(maxWidth: 320)

        Button(action: onContinue) {
          Text("Continue")
            .font(PWTypography.headline)
            .foregroundColor(PWColor.textPrimary)
            .padding(.horizontal, 28)
            .frame(height: 52)
            .background(
              Capsule(style: .continuous)
                .fill(PWColor.surfaceRaised)
            )
            .overlay(
              Capsule(style: .continuous)
                .stroke(PWColor.borderStrong, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)

        Text("Or tap anywhere")
          .font(PWTypography.caption)
          .foregroundColor(PWColor.textTertiary)

        Spacer(minLength: 0)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    .contentShape(Rectangle())
    .onTapGesture {
      onContinue()
    }
  }
}
