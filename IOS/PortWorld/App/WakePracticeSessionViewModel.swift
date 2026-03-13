import Combine
import Foundation

@MainActor
final class WakePracticeSessionViewModel: ObservableObject {
  enum Stage {
    case wake
    case sleep
    case completed
  }

  enum FeedbackTone {
    case neutral
    case success
    case retry
    case error
  }

  @Published private(set) var stage: Stage = .wake
  @Published private(set) var wakeCount = 0
  @Published private(set) var sleepCount = 0
  @Published private(set) var isListening = false
  @Published private(set) var feedbackTitle = "Ready?"
  @Published private(set) var feedbackDetail = "We’ll listen for your phrase three times."
  @Published private(set) var feedbackTone: FeedbackTone = .neutral
  @Published private(set) var errorText = ""

  let wakePhrase: String
  let sleepPhrase: String

  private let phoneAudioIO = PhoneAudioIO(preferSpeakerOutput: false)
  private let wakePhraseDetector: WakePhraseDetector
  private var feedbackResetTask: Task<Void, Never>?
  private var attemptTimeoutTask: Task<Void, Never>?

  init(config: AssistantRuntimeConfig) {
    self.wakePhrase = config.wakePhrase
    self.sleepPhrase = config.sleepPhrase
    self.wakePhraseDetector = WakePhraseDetector(config: config)

    phoneAudioIO.onWakePCMFrame = { [weak self] frame in
      self?.wakePhraseDetector.processPCMFrame(frame)
    }

    wakePhraseDetector.onWakeDetected = { [weak self] _ in
      Task { @MainActor [weak self] in
        self?.handleWakeDetected()
      }
    }

    wakePhraseDetector.onSleepDetected = { [weak self] _ in
      Task { @MainActor [weak self] in
        self?.handleSleepDetected()
      }
    }

    wakePhraseDetector.onError = { [weak self] message in
      Task { @MainActor [weak self] in
        self?.errorText = message
        self?.feedbackTitle = "Try again"
        self?.feedbackDetail = message
        self?.feedbackTone = .error
      }
    }

    wakePhraseDetector.onStatusChanged = { [weak self] status in
      Task { @MainActor [weak self] in
        self?.handleStatusChanged(status)
      }
    }
  }

  deinit {
    feedbackResetTask?.cancel()
    attemptTimeoutTask?.cancel()
  }

  func startListening() async {
    errorText = ""

    let authorization = await wakePhraseDetector.requestAuthorizationIfNeeded()
    guard authorization == .authorized || authorization == .notRequired else {
      errorText = "Speech recognition permission is required to test your voice commands."
      feedbackTitle = "Permission needed"
      feedbackDetail = errorText
      feedbackTone = .error
      return
    }

    do {
      try await phoneAudioIO.prepareForArmedListening()
      wakePhraseDetector.startArmedListening()
      isListening = true
      refreshNeutralFeedback()
      scheduleAttemptTimeout()
    } catch {
      errorText = error.localizedDescription
      feedbackTitle = "Microphone unavailable"
      feedbackDetail = error.localizedDescription
      feedbackTone = .error
    }
  }

  func stopListening() async {
    feedbackResetTask?.cancel()
    attemptTimeoutTask?.cancel()
    wakePhraseDetector.stop()
    await phoneAudioIO.stop()
    isListening = false
    if stage != .completed {
      refreshNeutralFeedback()
    }
  }

  private func handleWakeDetected() {
    guard isListening else { return }
    guard stage == .wake else { return }
    guard wakeCount < 3 else { return }

    wakeCount += 1
    showSuccessFeedback(detail: "\(wakeCount) of 3 complete")

    if wakeCount == 3 {
      transitionToSleepStage()
    } else {
      scheduleFeedbackReset()
    }
  }

  private func handleSleepDetected() {
    guard isListening else { return }
    guard stage == .sleep else { return }
    guard sleepCount < 3 else { return }

    sleepCount += 1
    showSuccessFeedback(detail: "\(sleepCount) of 3 complete")

    if sleepCount == 3 {
      stage = .completed
      feedbackTitle = "All set"
      feedbackDetail = "Both phrases were detected three times."
      feedbackTone = .success
      Task { await stopListening() }
    } else {
      scheduleFeedbackReset()
    }
  }

  private func transitionToSleepStage() {
    feedbackResetTask?.cancel()
    attemptTimeoutTask?.cancel()
    feedbackTitle = "Great!"
    feedbackDetail = "Now let’s practice your sleep phrase."
    feedbackTone = .success

    Task { @MainActor [weak self] in
      try? await Task.sleep(nanoseconds: 900_000_000)
      guard let self else { return }
      self.stage = .sleep
      self.refreshNeutralFeedback()
      self.scheduleAttemptTimeout()
    }
  }

  private func showSuccessFeedback(detail: String) {
    feedbackResetTask?.cancel()
    attemptTimeoutTask?.cancel()
    feedbackTitle = "Great!"
    feedbackDetail = detail
    feedbackTone = .success
  }

  private func scheduleFeedbackReset() {
    feedbackResetTask?.cancel()
    feedbackResetTask = Task { @MainActor [weak self] in
      try? await Task.sleep(nanoseconds: 900_000_000)
      guard let self else { return }
      self.refreshNeutralFeedback()
      self.scheduleAttemptTimeout()
    }
  }

  private func scheduleAttemptTimeout() {
    attemptTimeoutTask?.cancel()
    attemptTimeoutTask = Task { @MainActor [weak self] in
      try? await Task.sleep(nanoseconds: 6_000_000_000)
      guard let self else { return }
      guard self.isListening else { return }
      guard self.stage != .completed else { return }
      self.feedbackTitle = "Try again"
      self.feedbackDetail = self.stage == .wake
        ? "We didn’t catch \"\(self.displayWakePhrase)\" that time."
        : "We didn’t catch \"\(self.displaySleepPhrase)\" that time."
      self.feedbackTone = .retry
      self.scheduleFeedbackReset()
    }
  }

  private func refreshNeutralFeedback() {
    switch stage {
    case .wake:
      feedbackTitle = isListening ? "Listening..." : "Ready?"
      feedbackDetail = "Say \"\(displayWakePhrase)\" clearly."
    case .sleep:
      feedbackTitle = isListening ? "Listening..." : "Ready?"
      feedbackDetail = "Say \"\(displaySleepPhrase)\" clearly."
    case .completed:
      feedbackTitle = "All set"
      feedbackDetail = "Both phrases were detected three times."
    }
    feedbackTone = .neutral
  }

  private func handleStatusChanged(_ status: WakePhraseDetector.StatusSnapshot) {
    if status.authorization == "denied" || status.authorization == "restricted" {
      errorText = "Speech recognition permission is required to test your voice commands."
      feedbackTitle = "Permission needed"
      feedbackDetail = errorText
      feedbackTone = .error
    }
  }

  private var displayWakePhrase: String {
    formattedPhrase(wakePhrase)
  }

  private var displaySleepPhrase: String {
    formattedPhrase(sleepPhrase)
  }

  private func formattedPhrase(_ phrase: String) -> String {
    phrase
      .split(separator: " ")
      .map { $0.prefix(1).uppercased() + $0.dropFirst().lowercased() }
      .joined(separator: " ")
  }
}
