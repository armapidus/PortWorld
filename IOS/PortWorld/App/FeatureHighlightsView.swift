import SwiftUI

struct FeatureHighlightsView: View {
  let onContinue: () -> Void

  var body: some View {
    PWScreen {
      VStack(alignment: .leading, spacing: PWSpace.hero) {
        Spacer(minLength: 0)

        VStack(alignment: .leading, spacing: PWSpace.md) {
          Text("What PortWorld gives you")
            .font(PWTypography.display)
            .foregroundColor(PWColor.textPrimary)

          Text("Three things matter on day one.")
            .font(PWTypography.body)
            .foregroundColor(PWColor.textSecondary)
        }

        VStack(alignment: .leading, spacing: PWSpace.xl) {
          FeatureRow(
            systemImage: "waveform.and.mic",
            title: "Live voice agents",
            detail: "Talk naturally through your glasses and keep the interaction hands-free."
          )

          FeatureRow(
            systemImage: "person.crop.circle.badge.checkmark",
            title: "Personal context",
            detail: "Keep your profile, preferences, and projects connected to your own backend."
          )

          FeatureRow(
            systemImage: "eye",
            title: "Real-time capture",
            detail: "Send what you see to your agents without pulling out your phone."
          )
        }

        PWOnboardingButton(title: "Continue", action: onContinue)

        Spacer(minLength: 0)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
  }
}

private struct FeatureRow: View {
  let systemImage: String
  let title: String
  let detail: String

  var body: some View {
    HStack(alignment: .top, spacing: PWSpace.lg) {
      Image(systemName: systemImage)
        .font(.system(size: 18, weight: .semibold))
        .foregroundColor(PWColor.textPrimary)
        .frame(width: 40, height: 40)
        .background(
          Circle()
            .fill(PWColor.surface)
        )
        .overlay(
          Circle()
            .stroke(PWColor.borderSubtle, lineWidth: 1)
        )

      VStack(alignment: .leading, spacing: PWSpace.sm) {
        Text(title)
          .font(PWTypography.title)
          .foregroundColor(PWColor.textPrimary)

        Text(detail)
          .font(PWTypography.body)
          .foregroundColor(PWColor.textSecondary)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
  }
}
