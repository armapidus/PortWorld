import SwiftUI

extension AssistantRuntimeController {
  func activate() async {
    guard snapshot.assistantRuntimeState == .inactive else { return }
    snapshot.errorText = ""
    snapshot.infoText = "Preparing phone microphone, speaker playback, and wake detection."
    publishSnapshot()

    let authorization = await wakePhraseDetector.requestAuthorizationIfNeeded()
    if authorization != .authorized && authorization != .notRequired {
      snapshot.assistantRuntimeState = .inactive
      snapshot.errorText = "Wake phrase authorization unavailable: \(authorization.rawValue)"
      snapshot.infoText = ""
      await refreshSubsystemStatus()
      publishSnapshot()
      return
    }

    do {
      try await phoneAudioIO.prepareForArmedListening()
    } catch {
      snapshot.assistantRuntimeState = .inactive
      snapshot.errorText = error.localizedDescription
      snapshot.infoText = ""
      await refreshSubsystemStatus()
      publishSnapshot()
      return
    }

    backendReady = false
    firstUplinkAckReceived = false
    isSuppressingRealtimeUplinkForPlayback = false
    awaitingFirstWakePCMFrame = false
    activeConversationStartedAtMs = nil
    wakeListeningGeneration += 1
    snapshot.assistantRuntimeState = .armedListening
    snapshot.transportStatusText = "idle"
    snapshot.uplinkStatusText = "armed_waiting_for_wake"
    snapshot.playbackStatusText = "armed_waiting_for_response"
    snapshot.infoText = "Warming up wake detection."
    await refreshSubsystemStatus()
    publishSnapshot()
    scheduleWakeListeningStart(generation: wakeListeningGeneration)
  }

  func deactivate() async {
    guard snapshot.assistantRuntimeState != .inactive else { return }
    snapshot.assistantRuntimeState = .deactivating
    snapshot.infoText = "Stopping phone-only assistant."
    publishSnapshot()

    wakePhraseDetector.stop()
    wakeWarmupTask?.cancel()
    wakeWarmupTask = nil
    wakeListeningGeneration += 1
    await backendSessionClient.disconnect()
    await phoneAudioIO.stop()

    activeSessionID = nil
    backendReady = false
    firstUplinkAckReceived = false
    isSuppressingRealtimeUplinkForPlayback = false
    awaitingFirstWakePCMFrame = false
    activeConversationStartedAtMs = nil
    isResettingConversationToArmedState = false
    snapshot.assistantRuntimeState = .inactive
    snapshot.sessionID = "-"
    snapshot.transportStatusText = "disconnected"
    snapshot.uplinkStatusText = "idle"
    snapshot.playbackStatusText = "idle"
    snapshot.infoText = "Assistant inactive."
    await refreshSubsystemStatus()
    publishSnapshot()
  }

  func handleScenePhaseChange(_ phase: ScenePhase) {
    switch phase {
    case .background:
      guard snapshot.assistantRuntimeState != .inactive else { return }
      phoneAudioIO.prepareForBackground()
      if snapshot.assistantRuntimeState == .activeConversation {
        snapshot.infoText = "Active conversation continues while app is backgrounded if audio session remains available."
        snapshot.playbackRouteText = phoneAudioIO.playbackRouteDescription()
        publishSnapshot()
      }
    case .active:
      guard snapshot.assistantRuntimeState != .inactive else { return }
      phoneAudioIO.restoreFromForeground()
      snapshot.playbackRouteText = phoneAudioIO.playbackRouteDescription()
      publishSnapshot()
    case .inactive:
      break
    @unknown default:
      break
    }
  }

  func scheduleWakeListeningStart(generation: Int, readyMessage: String? = nil) {
    wakeWarmupTask?.cancel()
    wakeWarmupTask = Task { @MainActor [weak self] in
      guard let self else { return }
      guard wakeListeningGeneration == generation, snapshot.assistantRuntimeState == .armedListening else { return }
      if wakePhraseDetector.isListening == false {
        awaitingFirstWakePCMFrame = true
        snapshot.infoText = "Starting wake detection."
        publishSnapshot()
        debugLog("Starting wake recognizer for generation \(generation)")
        wakePhraseDetector.startArmedListening()
        snapshot.infoText = readyMessage ?? "Listening for microphone frames."
      } else {
        awaitingFirstWakePCMFrame = false
        snapshot.infoText = readyMessage ?? "Say \"\(config.wakePhrase)\" to start a conversation."
      }
      await refreshSubsystemStatus()
      publishSnapshot()
    }
  }
}
