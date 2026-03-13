import Combine
import Foundation

@MainActor
final class AppSettingsStore: ObservableObject {
  enum BackendValidationState: String, Codable {
    case unknown
    case valid
    case invalid
  }

  struct Settings: Codable, Equatable {
    var backendBaseURL: String
    var bearerToken: String
    var validationState: BackendValidationState
  }

  private static let settingsKey = "portworld.app.settings"

  @Published private(set) var settings: Settings

  private let userDefaults: UserDefaults
  private let encoder = JSONEncoder()
  private let decoder = JSONDecoder()

  init(userDefaults: UserDefaults = .standard, bundle: Bundle = .main) {
    self.userDefaults = userDefaults

    if let data = userDefaults.data(forKey: Self.settingsKey),
       let decoded = try? decoder.decode(Settings.self, from: data)
    {
      self.settings = decoded
    } else {
      let baseURL =
        (bundle.object(forInfoDictionaryKey: "SON_BACKEND_BASE_URL") as? String)?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      let bearerToken =
        (bundle.object(forInfoDictionaryKey: "SON_BEARER_TOKEN") as? String)?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      self.settings = Settings(
        backendBaseURL: baseURL,
        bearerToken: bearerToken,
        validationState: .unknown
      )
    }
  }
}
