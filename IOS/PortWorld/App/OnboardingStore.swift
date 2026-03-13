import Combine
import Foundation

@MainActor
final class OnboardingStore: ObservableObject {
  struct Progress: Codable, Equatable {
    var welcomeSeen = false
    var backendValidated = false
    var metaCompleted = false
    var metaSkipped = false
    var wakePracticeCompleted = false
    var profileCompleted = false
    var isFullyOnboarded = false
  }

  private static let progressKey = "portworld.onboarding.progress"

  @Published private(set) var progress: Progress

  private let userDefaults: UserDefaults
  private let encoder = JSONEncoder()
  private let decoder = JSONDecoder()

  init(userDefaults: UserDefaults = .standard) {
    self.userDefaults = userDefaults
    if let data = userDefaults.data(forKey: Self.progressKey),
       let decoded = try? decoder.decode(Progress.self, from: data)
    {
      self.progress = decoded
    } else {
      self.progress = Progress()
    }
  }

  var shouldShowWelcome: Bool {
    progress.welcomeSeen == false
  }

  func markWelcomeSeen() {
    guard progress.welcomeSeen == false else { return }
    progress.welcomeSeen = true
    persist()
  }

  func markBackendValidated() {
    guard progress.backendValidated == false else { return }
    progress.backendValidated = true
    persist()
  }

  private func persist() {
    guard let data = try? encoder.encode(progress) else { return }
    userDefaults.set(data, forKey: Self.progressKey)
  }
}
