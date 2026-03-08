// Bounded camera-session owner for periodic still-photo capture from Meta glasses.
import Foundation
import MWDATCamera
import MWDATCore
import UIKit

@MainActor
final class GlassesPhotoCaptureController {
  enum Phase: String {
    case inactive
    case requestingPermission = "requesting_permission"
    case starting
    case waitingForDevice = "waiting_for_device"
    case capturing
    case paused
    case stopping
    case failed
  }

  struct Snapshot {
    var phase: Phase = .inactive
    var errorMessage: String?
  }

  var onSnapshotUpdated: ((Snapshot) -> Void)?
  var onPhotoCaptured: ((UIImage, Int64) -> Void)?

  private let deviceSessionCoordinator: DeviceSessionCoordinator
  private var snapshot = Snapshot()
  private var captureLoopTask: Task<Void, Never>?
  private var isActive = false
  private var photoIntervalNs: UInt64 = 1_000_000_000

  init(wearables: WearablesInterface) {
    self.deviceSessionCoordinator = DeviceSessionCoordinator(wearables: wearables)
    bindHooks()
    publishSnapshot()
  }

  deinit {
    captureLoopTask?.cancel()
  }

  func start(photoFps: Double) async {
    photoIntervalNs = UInt64((1_000_000_000.0 / max(0.1, photoFps)).rounded())

    guard !isActive else {
      ensureCaptureLoop()
      return
    }

    isActive = true
    snapshot.errorMessage = nil
    snapshot.phase = .requestingPermission
    publishSnapshot()

    do {
      try await deviceSessionCoordinator.ensureCameraPermissionIfNeeded()
    } catch {
      isActive = false
      snapshot.phase = .failed
      snapshot.errorMessage = error.localizedDescription
      publishSnapshot()
      return
    }

    snapshot.phase = .starting
    publishSnapshot()
    await deviceSessionCoordinator.startSession()
    ensureCaptureLoop()
  }

  func stop() async {
    guard isActive || captureLoopTask != nil else {
      snapshot.phase = .inactive
      snapshot.errorMessage = nil
      publishSnapshot()
      return
    }

    isActive = false
    snapshot.phase = .stopping
    publishSnapshot()
    captureLoopTask?.cancel()
    captureLoopTask = nil
    await deviceSessionCoordinator.stopSession()
    snapshot.phase = .inactive
    snapshot.errorMessage = nil
    publishSnapshot()
  }

  private func bindHooks() {
    deviceSessionCoordinator.hooks.onPhotoCaptured = { [weak self] image, timestampMs in
      self?.onPhotoCaptured?(image, timestampMs)
    }

    deviceSessionCoordinator.hooks.onStreamError = { [weak self] error in
      guard let self else { return }
      self.snapshot.phase = .failed
      self.snapshot.errorMessage = DeviceSessionCoordinator.formatStreamingError(error)
      self.publishSnapshot()
    }

    deviceSessionCoordinator.hooks.onStreamingStateChanged = { [weak self] state in
      self?.applyStreamingState(state)
    }
  }

  private func applyStreamingState(_ state: StreamSessionState) {
    guard isActive else { return }

    switch state {
    case .starting:
      snapshot.phase = .starting
      snapshot.errorMessage = nil
    case .waitingForDevice:
      snapshot.phase = .waitingForDevice
    case .streaming:
      snapshot.phase = .capturing
      snapshot.errorMessage = nil
    case .paused:
      snapshot.phase = .paused
    case .stopping:
      snapshot.phase = .stopping
    case .stopped:
      snapshot.phase = .inactive
    @unknown default:
      snapshot.phase = .failed
      snapshot.errorMessage = "Unknown glasses photo capture state."
    }

    publishSnapshot()
  }

  private func ensureCaptureLoop() {
    guard captureLoopTask == nil else { return }

    captureLoopTask = Task { @MainActor [weak self] in
      guard let self else { return }
      while !Task.isCancelled {
        if isActive, snapshot.phase == .capturing {
          deviceSessionCoordinator.capturePhoto()
        }

        do {
          try await Task.sleep(nanoseconds: photoIntervalNs)
        } catch {
          break
        }
      }
    }
  }

  private func publishSnapshot() {
    onSnapshotUpdated?(snapshot)
  }
}
