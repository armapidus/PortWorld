import Combine
import MWDATCamera
import SwiftUI

@MainActor
final class RuntimeCoordinator {
  private let store: SessionStateStore
  private let deviceSessionCoordinator: DeviceSessionCoordinator
  private let audioCollectionManager: AudioCollectionManager
  private let runtimeOrchestrator: SessionOrchestrator
  private var audioStateCancellables = Set<AnyCancellable>()

  init(
    store: SessionStateStore,
    deviceSessionCoordinator: DeviceSessionCoordinator,
    runtimeConfig: RuntimeConfig
  ) {
    self.store = store
    self.deviceSessionCoordinator = deviceSessionCoordinator
    self.audioCollectionManager = AudioCollectionManager(
      speechRMSThreshold: runtimeConfig.speechRMSThreshold,
      speechActivityDebounceMs: runtimeConfig.speechActivityDebounceMs
    )
    let audioManager = self.audioCollectionManager

    let dependencies = SessionOrchestrator.Dependencies(
      startStream: {
        await audioManager.prepareAudioSession()
        if audioManager.isAudioSessionReady {
          await audioManager.start()
        }
        await deviceSessionCoordinator.startSession()
      },
      stopStream: {
        await audioManager.stop()
        await deviceSessionCoordinator.stopSession()
      },
      exportAudioClip: { window in
        try audioManager.exportWAVClip(window: window)
      },
      flushPendingAudioChunks: {
        audioManager.flushPendingAudioChunks()
      },
      audioBufferDurationProvider: {
        let bytes = audioManager.stats.bytesWritten
        return Int(bytes / 16)
      },
      sharedAudioEngine: audioManager.sharedAudioEngine,
      clock: { Clocks.nowMs() },
      makeWebSocketClient: SessionOrchestrator.Dependencies.live.makeWebSocketClient,
      makeVisionFrameUploader: SessionOrchestrator.Dependencies.live.makeVisionFrameUploader,
      makeRollingVideoBuffer: SessionOrchestrator.Dependencies.live.makeRollingVideoBuffer,
      makeQueryBundleBuilder: SessionOrchestrator.Dependencies.live.makeQueryBundleBuilder,
      makePlaybackEngine: SessionOrchestrator.Dependencies.live.makePlaybackEngine,
      eventLogger: SessionOrchestrator.Dependencies.live.eventLogger
    )

    self.runtimeOrchestrator = SessionOrchestrator(config: runtimeConfig, dependencies: dependencies)
    bindDeviceSession()
    bindRuntimeState()
    bindAudioState()
  }

  func activate() async {
    await runtimeOrchestrator.preflightWakeAuthorization()
    await runtimeOrchestrator.activate()
  }

  func deactivate() async {
    await runtimeOrchestrator.deactivate()
  }

  func triggerWakeForTesting() {
    runtimeOrchestrator.triggerWakeForTesting()
  }

  func pushVideoFrame(_ image: UIImage, timestampMs: Int64) {
    runtimeOrchestrator.pushVideoFrame(image, timestampMs: timestampMs)
  }

  func submitCapturedPhoto(_ image: UIImage, timestampMs: Int64) {
    runtimeOrchestrator.submitCapturedPhoto(image, timestampMs: timestampMs)
  }

  func recordSpeechActivity(_ timestampMs: Int64) {
    runtimeOrchestrator.recordSpeechActivity(at: timestampMs)
  }

  func processWakePCMFrame(_ frame: WakeWordPCMFrame) {
    runtimeOrchestrator.processWakePCMFrame(frame)
  }

  func handleScenePhaseChange(_ phase: ScenePhase) {
    switch phase {
    case .active:
      runtimeOrchestrator.handleAppDidBecomeActive()
    case .inactive:
      runtimeOrchestrator.handleAppWillResignActive()
    case .background:
      runtimeOrchestrator.handleAppDidEnterBackground()
    @unknown default:
      break
    }
  }

  var onWakeAuthorizationPreflight: (() async -> Void)?

  func preflightWakeAuthorization() async {
    await runtimeOrchestrator.preflightWakeAuthorization()
  }

  private func bindDeviceSession() {
    deviceSessionCoordinator.hooks.onActiveDeviceChanged = { [weak self] hasDevice in
      self?.store.hasActiveDevice = hasDevice
    }

    deviceSessionCoordinator.hooks.onStreamingStateChanged = { [weak self] state in
      self?.updateStatusFromStreamState(state)
    }

    deviceSessionCoordinator.hooks.onStreamError = { [weak self] error in
      self?.showError(DeviceSessionCoordinator.formatStreamingError(error))
    }

    deviceSessionCoordinator.hooks.onVideoFrame = { [weak self] image, timestampMs in
      guard let self else { return }
      store.currentVideoFrame = image
      if !store.hasReceivedFirstFrame {
        store.hasReceivedFirstFrame = true
      }
      runtimeOrchestrator.pushVideoFrame(image, timestampMs: timestampMs)
    }

    deviceSessionCoordinator.hooks.onPhotoCaptured = { [weak self] image, timestampMs in
      guard let self else { return }
      store.capturedPhoto = image
      store.showPhotoPreview = true
      store.runtimePhotoStateText = "captured"
      runtimeOrchestrator.submitCapturedPhoto(image, timestampMs: timestampMs)
    }
  }

  private func bindRuntimeState() {
    runtimeOrchestrator.onStatusUpdated = { [weak self] snapshot in
      guard let self else { return }
      store.runtimeSessionStateText = snapshot.sessionState.rawValue
      store.runtimeWakeStateText = snapshot.wakeState.rawValue
      store.runtimeQueryStateText = snapshot.queryState.rawValue
      store.runtimePhotoStateText = snapshot.photoState.rawValue
      store.runtimePlaybackStateText = snapshot.playbackState
      store.runtimeWakeEngineText = snapshot.wakeEngine
      store.runtimeWakeRuntimeText = snapshot.wakeRuntimeStatus
      store.runtimeSpeechAuthorizationText = snapshot.speechAuthorization
      store.runtimeManualWakeFallbackText = snapshot.manualWakeFallbackEnabled ? "enabled" : "disabled"
      store.runtimeBackendText = snapshot.backendSummary
      store.runtimeSessionIdText = snapshot.sessionID
      store.runtimeQueryIdText = snapshot.queryID
      store.runtimeWakeCount = snapshot.wakeCount
      store.runtimeQueryCount = snapshot.queryCount
      store.runtimePhotoUploadCount = snapshot.photoUploadCount
      store.runtimePlaybackChunkCount = snapshot.playbackChunkCount
      store.runtimePendingPlaybackBufferCount = snapshot.pendingPlaybackBufferCount
      store.runtimeVideoFrameCount = snapshot.videoFrameCount
      store.runtimeErrorText = snapshot.lastError

      if store.assistantRuntimeState != .deactivating {
        switch snapshot.sessionState {
        case .idle, .ended:
          store.assistantRuntimeState = .inactive
        case .connecting, .reconnecting:
          store.assistantRuntimeState = .activating
        case .active:
          store.assistantRuntimeState = .active
        case .failed:
          store.assistantRuntimeState = .failed
        }
      }
    }

    audioCollectionManager.onWakePCMFrame = { [weak self] frame in
      self?.runtimeOrchestrator.processWakePCMFrame(frame)
    }
  }

  private func bindAudioState() {
    audioCollectionManager.$state
      .sink { [weak self] state in
        guard let self else { return }
        switch state {
        case .idle:
          store.audioStateText = "idle"
        case .preparingAudioSession:
          store.audioStateText = "preparing"
        case .waitingForDevice:
          store.audioStateText = "waiting_for_device"
        case .recording:
          store.audioStateText = "recording"
        case .stopping:
          store.audioStateText = "stopping"
        case .failed(let message):
          store.audioStateText = "failed: \(message)"
          store.audioLastError = message
          store.runtimeErrorText = message
        }
        store.isAudioRecording = state == .recording
      }
      .store(in: &audioStateCancellables)

    audioCollectionManager.$stats
      .sink { [weak self] stats in
        guard let self else { return }
        store.audioChunkCount = stats.chunksWritten
        store.audioByteCount = stats.bytesWritten
        store.audioStatsText = "Chunks: \(stats.chunksWritten)  Bytes: \(stats.bytesWritten)"
        if let lastError = stats.lastError {
          store.audioLastError = lastError
          store.runtimeErrorText = lastError
        }
      }
      .store(in: &audioStateCancellables)

    audioCollectionManager.$lastSpeechActivityTimestampMs
      .sink { [weak self] timestampMs in
        guard let self, let timestampMs else { return }
        runtimeOrchestrator.recordSpeechActivity(at: timestampMs)
      }
      .store(in: &audioStateCancellables)

    audioCollectionManager.$isAudioSessionReady
      .sink { [weak self] ready in
        self?.store.isAudioReady = ready
      }
      .store(in: &audioStateCancellables)

    audioCollectionManager.$currentSessionDirectory
      .sink { [weak self] directory in
        self?.store.audioSessionPath = directory?.path ?? "No audio session directory"
      }
      .store(in: &audioStateCancellables)
  }

  private func updateStatusFromStreamState(_ state: StreamSessionState) {
    switch state {
    case .stopped:
      store.currentVideoFrame = nil
      store.streamingStatus = .stopped
      if store.assistantRuntimeState == .deactivating {
        store.runtimeSessionStateText = "inactive"
      } else if store.assistantRuntimeState == .activating || store.assistantRuntimeState == .active {
        store.runtimeSessionStateText = "stopped"
      }
    case .waitingForDevice, .starting, .stopping, .paused:
      store.streamingStatus = .waiting
      if store.assistantRuntimeState != .inactive {
        store.runtimeSessionStateText = "waiting"
      }
    case .streaming:
      store.streamingStatus = .streaming
      if store.assistantRuntimeState == .activating || store.assistantRuntimeState == .active {
        store.runtimeSessionStateText = "active"
      }
    }
  }

  private func showError(_ message: String) {
    store.errorMessage = message
    store.showError = true
    store.runtimeErrorText = message

    if store.assistantRuntimeState == .activating || store.assistantRuntimeState == .active {
      store.assistantRuntimeState = .failed
      store.runtimeSessionStateText = "failed"
    }
  }
}
