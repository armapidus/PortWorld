import SwiftUI

struct BackendSetupView: View {
  @ObservedObject var appSettingsStore: AppSettingsStore

  let onValidationSuccess: () -> Void

  @State private var backendBaseURL: String
  @State private var bearerToken: String
  @State private var errorMessage = ""
  @State private var isValidating = false
  @FocusState private var focusedField: Field?

  private let validationClient = BackendValidationClient()

  init(
    appSettingsStore: AppSettingsStore,
    onValidationSuccess: @escaping () -> Void
  ) {
    self.appSettingsStore = appSettingsStore
    self.onValidationSuccess = onValidationSuccess
    _backendBaseURL = State(initialValue: appSettingsStore.settings.backendBaseURL)
    _bearerToken = State(initialValue: appSettingsStore.settings.bearerToken)
  }

  var body: some View {
    PWScreen {
      VStack(alignment: .leading, spacing: PWSpace.section) {
        VStack(alignment: .leading, spacing: PWSpace.md) {
          Text("Connect your backend")
            .font(PWTypography.display)
            .foregroundColor(PWColor.textPrimary)

          Text("Enter the URL of your self-hosted PortWorld backend. Add a bearer token if your deployment requires one.")
            .font(PWTypography.body)
            .foregroundColor(PWColor.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
        }

        PWCard {
          VStack(alignment: .leading, spacing: PWSpace.lg) {
            PWTextFieldRow(
              label: "Backend URL",
              placeholder: "https://your-backend.example.com",
              text: $backendBaseURL,
              message: backendURLMessage,
              tone: backendURLTone,
              textInputAutocapitalization: .never,
              keyboardType: .URL,
              submitLabel: .next
            )
            .focused($focusedField, equals: .backendURL)
            .onSubmit {
              focusedField = .bearerToken
            }

            PWTextFieldRow(
              label: "Bearer Token",
              placeholder: "Optional",
              text: $bearerToken,
              message: "Leave blank if your backend does not require authentication.",
              isSecure: true,
              textInputAutocapitalization: .never,
              submitLabel: .go
            )
            .focused($focusedField, equals: .bearerToken)
            .onSubmit {
              Task { await validateAndContinue() }
            }
          }
        }

        if statusMessage.isEmpty == false {
          PWStatusRow(
            title: statusTitle,
            value: statusMessage,
            tone: statusTone,
            systemImage: statusSymbol
          )
        }

        Spacer(minLength: 0)
      }
    }
    .safeAreaInset(edge: .bottom) {
      PWBottomActionBar {
        PWPrimaryButton(title: isValidating ? "Validating..." : "Continue", isDisabled: isContinueDisabled) {
          Task { await validateAndContinue() }
        }
      }
    }
  }
}

private extension BackendSetupView {
  enum Field {
    case backendURL
    case bearerToken
  }

  var isContinueDisabled: Bool {
    isValidating || backendBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  var backendURLTone: PWFieldTone {
    if errorMessage.isEmpty == false { return .error }
    if appSettingsStore.settings.validationState == .valid &&
      normalized(backendBaseURL) == appSettingsStore.settings.backendBaseURL
    {
      return .success
    }
    return .normal
  }

  var backendURLMessage: String? {
    if errorMessage.isEmpty == false {
      return errorMessage
    }

    if appSettingsStore.settings.validationState == .valid &&
      normalized(backendBaseURL) == appSettingsStore.settings.backendBaseURL
    {
      return "Backend connection verified."
    }

    return "Use the base URL only. The app derives the required endpoints automatically."
  }

  var statusTitle: String {
    if isValidating {
      return "Checking backend"
    }

    switch appSettingsStore.settings.validationState {
    case .valid:
      return "Backend ready"
    case .invalid:
      return "Validation failed"
    case .unknown:
      return ""
    }
  }

  var statusMessage: String {
    if isValidating {
      return "Checking connectivity and deployment readiness."
    }

    if errorMessage.isEmpty == false {
      return errorMessage
    }

    switch appSettingsStore.settings.validationState {
    case .valid:
      return "The backend is reachable and ready for onboarding."
    case .invalid, .unknown:
      return ""
    }
  }

  var statusTone: PWStatusTone {
    if isValidating { return .neutral }
    if errorMessage.isEmpty == false { return .error }
    return appSettingsStore.settings.validationState == .valid ? .success : .neutral
  }

  var statusSymbol: String? {
    if isValidating { return "network" }
    if errorMessage.isEmpty == false { return "exclamationmark.triangle" }
    return appSettingsStore.settings.validationState == .valid ? "checkmark.circle" : nil
  }

  func validateAndContinue() async {
    let trimmedURL = normalized(backendBaseURL)
    let trimmedToken = normalized(bearerToken)

    isValidating = true
    errorMessage = ""

    do {
      try await validationClient.validate(baseURLString: trimmedURL, bearerToken: trimmedToken)
      appSettingsStore.updateBackendSettings(
        backendBaseURL: trimmedURL,
        bearerToken: trimmedToken,
        validationState: .valid
      )
      isValidating = false
      onValidationSuccess()
    } catch let error as BackendValidationClient.ValidationError {
      appSettingsStore.updateBackendSettings(
        backendBaseURL: trimmedURL,
        bearerToken: trimmedToken,
        validationState: .invalid
      )
      errorMessage = error.errorDescription ?? "Validation failed."
      isValidating = false
    } catch {
      appSettingsStore.updateBackendSettings(
        backendBaseURL: trimmedURL,
        bearerToken: trimmedToken,
        validationState: .invalid
      )
      errorMessage = "Validation failed."
      isValidating = false
    }
  }

  func normalized(_ value: String) -> String {
    value.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
