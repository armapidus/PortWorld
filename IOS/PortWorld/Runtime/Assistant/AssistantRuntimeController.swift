import Foundation

@MainActor
final class AssistantRuntimeController {
  struct PendingRealtimeFrame {
    let payload: Data
    let timestampMs: Int64
  }

  struct StatusSnapshot {
    var assistantRuntimeState: PhoneAssistantRuntimeState = .inactive
    var audioStatusText: String = "idle"
    var backendStatusText: String = "idle"
    var wakeStatusText: String = "idle"
    var wakePhraseText: String = ""
    var sleepPhraseText: String = ""
    var sessionID: String = "-"
    var transportStatusText: String = "disconnected"
    var uplinkStatusText: String = "idle"
    var playbackStatusText: String = "idle"
    var playbackRouteText: String = "-"
    var infoText: String = ""
    var errorText: String = ""
  }

  let config: PhoneOnlyRuntimeConfig
  let phoneAudioIO: PhoneAudioIO
  let backendSessionClient: BackendSessionClient
  let wakePhraseDetector: WakePhraseDetector

  var wakeWarmupTask: Task<Void, Never>?
  var wakeListeningGeneration: Int = 0
  var activeSessionID: String?
  var backendReady = false
  var firstUplinkAckReceived = false
  var isSuppressingRealtimeUplinkForPlayback = false
  var awaitingFirstWakePCMFrame = false
  var activeConversationStartedAtMs: Int64?
  var isResettingConversationToArmedState = false
  var pendingRealtimeFrames: [PendingRealtimeFrame] = []
  let maxPendingRealtimeFrames = 24

  var snapshot: StatusSnapshot
  var onStatusUpdated: ((StatusSnapshot) -> Void)?

  init(
    config: PhoneOnlyRuntimeConfig,
    phoneAudioIO: PhoneAudioIO? = nil,
    backendSessionClient: BackendSessionClient? = nil,
    wakePhraseDetector: WakePhraseDetector? = nil
  ) {
    self.config = config
    self.phoneAudioIO = phoneAudioIO ?? PhoneAudioIO()
    self.backendSessionClient = backendSessionClient ?? BackendSessionClient(
      webSocketURL: config.webSocketURL,
      requestHeaders: config.requestHeaders
    )
    self.wakePhraseDetector = wakePhraseDetector ?? WakePhraseDetector(config: config)
    self.snapshot = StatusSnapshot(
      wakePhraseText: config.wakePhrase,
      sleepPhraseText: config.sleepPhrase,
      infoText: "Phone-only assistant ready."
    )

    bindPhoneAudio()
    bindWakePhraseDetector()
    bindBackendEvents()
  }

  deinit {
    wakeWarmupTask?.cancel()
    let backendSessionClient = self.backendSessionClient
    Task {
      await backendSessionClient.setEventHandler(nil)
    }
  }

  func bindPhoneAudio() {
    phoneAudioIO.onWakePCMFrame = { [weak self] frame in
      guard let self else { return }
      if self.awaitingFirstWakePCMFrame, self.snapshot.assistantRuntimeState == .armedListening {
        self.awaitingFirstWakePCMFrame = false
        self.snapshot.infoText = "Say \"\(self.config.wakePhrase)\" to start a conversation."
        self.debugLog("Received first wake PCM frame after arming")
        self.publishSnapshot()
      }
      self.wakePhraseDetector.processPCMFrame(frame)
    }
    phoneAudioIO.onRealtimePCMFrame = { [weak self] payload, timestampMs in
      Task { @MainActor [weak self] in
        await self?.handleRealtimePCMFrame(payload, timestampMs: timestampMs)
      }
    }
  }

  func bindWakePhraseDetector() {
    wakePhraseDetector.onWakeDetected = { [weak self] event in
      Task { @MainActor [weak self] in
        await self?.startConversation(from: event)
      }
    }
    wakePhraseDetector.onSleepDetected = { [weak self] event in
      Task { @MainActor [weak self] in
        await self?.handleSleepDetected(event)
      }
    }
    wakePhraseDetector.onError = { [weak self] message in
      self?.snapshot.errorText = message
      self?.publishSnapshot()
    }
  }

  func refreshSubsystemStatus() async {
    let wakeStatus = wakePhraseDetector.statusSnapshot()
    let diagnostics = await backendSessionClient.diagnosticsSnapshot()
    snapshot.audioStatusText = phoneAudioIO.stateDescription()
    snapshot.backendStatusText = await backendSessionClient.connectionStateText()
    snapshot.wakeStatusText = wakeStatus.runtime
    snapshot.playbackRouteText = phoneAudioIO.playbackRouteDescription()
    if snapshot.assistantRuntimeState == .inactive {
      snapshot.playbackStatusText = "idle"
    } else if snapshot.playbackStatusText == "idle" {
      let inboundFrames = diagnostics.inboundServerAudioFrameCount
      if inboundFrames > 0 {
        snapshot.playbackStatusText = "received frames=\(inboundFrames) bytes=\(diagnostics.inboundServerAudioBytes)"
      } else if diagnostics.lastPlaybackControlCommand != "none" {
        snapshot.playbackStatusText = diagnostics.lastPlaybackControlCommand
      }
    }
    if !firstUplinkAckReceived && (snapshot.transportStatusText == "ready" || snapshot.transportStatusText == "connected") {
      snapshot.uplinkStatusText = "binary_completed=\(diagnostics.binarySendSuccessCount)"
    }
  }

  func publishSnapshot() {
    onStatusUpdated?(snapshot)
  }

  func debugLog(_ message: String) {
    #if DEBUG
      print("[AssistantRuntimeController] \(message)")
    #endif
  }
}
