import AVFAudio
import Foundation
import OSLog

public enum AssistantPlaybackError: Error, LocalizedError {
  case invalidBase64Chunk
  case unsupportedCodec(String)
  case unsupportedSampleRate(Int)
  case unsupportedChannelCount(Int)
  case invalidPCMByteCount(Int)
  case formatMismatch(expected: AssistantAudioFormat, received: AssistantAudioFormat)
  case unableToBuildAudioFormat
  case unableToAllocateBuffer
  case outputChannelMismatch(expected: Int, actual: Int)
  case engineStartFailed(String)
  case invalidAudioSessionCategory(expected: String, actual: String)

  public var errorDescription: String? {
    switch self {
    case .invalidBase64Chunk:
      return "Audio chunk payload is not valid base64."
    case .unsupportedCodec(let codec):
      return "Unsupported audio codec '\(codec)'. Expected pcm_s16le."
    case .unsupportedSampleRate(let sampleRate):
      return "Unsupported sample rate '\(sampleRate)'. Expected 16000 Hz."
    case .unsupportedChannelCount(let channels):
      return "Unsupported channel count '\(channels)'. Only mono is supported."
    case .invalidPCMByteCount(let count):
      return "PCM payload byte count \(count) is not aligned to 16-bit mono samples."
    case .formatMismatch(let expected, let received):
      return "Audio format mismatch. Expected \(expected.description), received \(received.description)."
    case .unableToBuildAudioFormat:
      return "Unable to build AVAudioFormat for assistant playback."
    case .unableToAllocateBuffer:
      return "Unable to allocate playback audio buffer."
    case .outputChannelMismatch(let expected, let actual):
      return "Playback output channel mismatch. Expected \(expected), got \(actual)."
    case .engineStartFailed(let message):
      return "Failed to start playback engine: \(message)"
    case .invalidAudioSessionCategory(let expected, let actual):
      return "Invalid audio session category '\(actual)'. Expected '\(expected)' before assistant playback."
    }
  }
}

public struct AssistantAudioFormat: Equatable {
  public let codec: String
  public let sampleRate: Int
  public let channels: Int

  public init(codec: String, sampleRate: Int, channels: Int) {
    self.codec = codec
    self.sampleRate = sampleRate
    self.channels = channels
  }

  fileprivate var description: String {
    "\(codec)@\(sampleRate)Hz/\(channels)ch"
  }
}

struct AssistantPlaybackQueueState {
  private(set) var pendingBufferCount: Int = 0
  private(set) var pendingBufferDurationMs: Double = 0
  private(set) var lastBufferDrainedAtMs: Int64 = 0
  private(set) var lastBufferScheduledAtMs: Int64 = 0
  private(set) var consecutiveStuckChecks: Int = 0

  mutating func recordScheduledBuffer(durationMs: Double, nowMs: Int64) {
    pendingBufferCount += 1
    pendingBufferDurationMs += durationMs
    lastBufferScheduledAtMs = nowMs
  }

  mutating func recordBufferDrained(durationMs: Double, nowMs: Int64) {
    if pendingBufferCount > 0 {
      pendingBufferCount -= 1
    } else {
      pendingBufferCount = 0
    }

    if pendingBufferDurationMs >= durationMs {
      pendingBufferDurationMs -= durationMs
    } else {
      pendingBufferDurationMs = 0
    }

    lastBufferDrainedAtMs = nowMs
  }

  mutating func shouldAttemptRecovery(
    nowMs: Int64,
    thresholdMs: Int64,
    maxConsecutiveChecks: Int
  ) -> Bool {
    guard pendingBufferCount > 0, lastBufferScheduledAtMs > 0 else {
      return false
    }

    let timeSinceLastDrain = nowMs - lastBufferDrainedAtMs
    let timeSinceLastSchedule = nowMs - lastBufferScheduledAtMs

    if timeSinceLastSchedule < 500 && timeSinceLastDrain > thresholdMs {
      consecutiveStuckChecks += 1
      return consecutiveStuckChecks >= maxConsecutiveChecks
    }

    if timeSinceLastDrain < thresholdMs {
      consecutiveStuckChecks = 0
    }
    return false
  }

  mutating func resetForStartResponse(nowMs: Int64) {
    pendingBufferCount = 0
    pendingBufferDurationMs = 0
    consecutiveStuckChecks = 0
    lastBufferScheduledAtMs = 0
    lastBufferDrainedAtMs = nowMs
  }

  mutating func resetForCancelResponse() {
    pendingBufferCount = 0
    pendingBufferDurationMs = 0
    consecutiveStuckChecks = 0
  }

  mutating func resetForRecovery(nowMs: Int64) {
    pendingBufferCount = 0
    pendingBufferDurationMs = 0
    consecutiveStuckChecks = 0
    lastBufferDrainedAtMs = nowMs
  }
}

@MainActor
public final class AssistantPlaybackEngine: AssistantPlaybackEngineProtocol {
  public var onRouteChanged: ((String) -> Void)?
  public var onRouteIssue: ((String) -> Void)?

  private let audioSession: AVAudioSession
  private let audioEngine: AVAudioEngine
  private let playerNode: AVAudioPlayerNode
  private let ownsEngine: Bool
  private var currentFormat: AssistantAudioFormat?
  private var routeObserver: NSObjectProtocol?
  private var interruptionObserver: NSObjectProtocol?
  private var isPlayerNodeAttached = false
  private var isPlayerNodeConnected = false
  private static let graphFormat = AssistantAudioFormat(codec: "pcm_s16le", sampleRate: 16_000, channels: 1)
  private static let logger = Logger(
    subsystem: Bundle.main.bundleIdentifier ?? "PortWorld",
    category: "AssistantPlaybackEngine"
  )
  private var queueState = AssistantPlaybackQueueState()

  /// Threshold (ms) for detecting stuck playback. If buffers were scheduled
  /// this recently but no drain callback fired, we may be stuck.
  private let stuckDetectionThresholdMs: Int64
  private let nowMsProvider: () -> Int64

  /// Max consecutive stuck checks before attempting recovery.
  private static let maxStuckChecksBeforeRecovery: Int = 3

  /// Maximum pending audio duration (ms) before backpressure kicks in.
  /// 3 seconds balances latency vs. resilience to Bluetooth HFP drain variability.
  private static let maxPendingDurationMs: Double = 3000

  /// High water mark (ms) at which we signal backpressure to callers.
  /// Set lower than maxPendingDurationMs to allow proactive throttling.
  private static let backpressureHighWaterMs: Double = 1500

  /// Whether the playback queue is under backpressure (pending audio exceeds high water mark).
  /// Callers can use this to throttle upstream chunk generation.
  public var pendingBufferCount: Int { queueState.pendingBufferCount }
  public var pendingBufferDurationMs: Double { queueState.pendingBufferDurationMs }

  public var isBackpressured: Bool {
    pendingBufferDurationMs > Self.backpressureHighWaterMs
  }

  public func hasActivePendingPlayback() -> Bool {
    pendingBufferCount > 0
  }

  /// Maximum number of pending buffers before backpressure kicks in.
  /// At ~100ms per buffer chunk, 50 buffers ≈ 5 seconds of queued audio.
  private static let maxPendingBuffers = 50

  /// Creates a playback engine.
  /// - Parameters:
  ///   - audioSession: The AVAudioSession to use for route information.
  ///   - audioEngine: The AVAudioEngine to attach the player node to. If nil, creates a new engine internally.
  ///   - playerNode: The player node for audio playback.
  public init(
    audioSession: AVAudioSession = .sharedInstance(),
    audioEngine: AVAudioEngine? = nil,
    playerNode: AVAudioPlayerNode = AVAudioPlayerNode(),
    stuckDetectionThresholdMs: Int64 = 1_500
  ) {
    self.audioSession = audioSession
    if let audioEngine {
      self.audioEngine = audioEngine
      self.ownsEngine = false
    } else {
      self.audioEngine = AVAudioEngine()
      self.ownsEngine = true
    }
    self.playerNode = playerNode
    self.stuckDetectionThresholdMs = max(250, stuckDetectionThresholdMs)
    self.nowMsProvider = { Clocks.nowMs() }

    // Attach once, then connect lazily from the first inbound chunk format.
    // Avoid disconnect/reconnect churn on a shared engine.
    ensurePlayerNodeAttached()
    do {
      try connectPlayerNodeIfNeeded(for: Self.graphFormat)
      currentFormat = Self.graphFormat
    } catch {
      debugLog("[AssistantPlaybackEngine] Failed to connect playback graph at init: \(error.localizedDescription)")
    }

    routeObserver = NotificationCenter.default.addObserver(
      forName: AVAudioSession.routeChangeNotification,
      object: audioSession,
      queue: .main
    ) { [weak self] notification in
      MainActor.assumeIsolated {
        self?.publishRouteUpdate(notification: notification)
      }
    }

    interruptionObserver = NotificationCenter.default.addObserver(
      forName: AVAudioSession.interruptionNotification,
      object: audioSession,
      queue: .main
    ) { [weak self] notification in
      let interruptionType = Self.interruptionType(from: notification)
      MainActor.assumeIsolated {
        self?.handleInterruption(interruptionType)
      }
    }
  }

  deinit {
    if let routeObserver {
      NotificationCenter.default.removeObserver(routeObserver)
    }
    if let interruptionObserver {
      NotificationCenter.default.removeObserver(interruptionObserver)
    }
  }

  public func configureBluetoothHFPRoute() throws {
    // AudioCollectionManager owns AVAudioSession lifecycle/category for capture+playback.
    // Playback intentionally avoids mutating shared AVAudioSession state.
    // Log current routing state for diagnostics.
    logCurrentRouteState(context: "configureBluetoothHFPRoute")
  }

  /// Logs detailed audio session routing state for diagnostics.
  private func logCurrentRouteState(context: String) {
    let route = audioSession.currentRoute
    let inputPorts = route.inputs.map { "\($0.portType.rawValue):\($0.portName)" }.joined(separator: ", ")
    let outputPorts = route.outputs.map { "\($0.portType.rawValue):\($0.portName)" }.joined(separator: ", ")
    let category = audioSession.category.rawValue
    let mode = audioSession.mode.rawValue
    debugLog("[AssistantPlaybackEngine] Route state (\(context)): category=\(category), mode=\(mode), inputs=[\(inputPorts)], outputs=[\(outputPorts)]")
  }

  public func appendChunk(_ payload: AssistantAudioChunkPayload) throws {
    guard payload.codec.lowercased() == "pcm_s16le" else {
      throw AssistantPlaybackError.unsupportedCodec(payload.codec)
    }
    guard payload.channels == 1 else {
      throw AssistantPlaybackError.unsupportedChannelCount(payload.channels)
    }
    guard let pcmData = Data(base64Encoded: payload.bytesB64) else {
      throw AssistantPlaybackError.invalidBase64Chunk
    }

    try appendPCMData(
      pcmData,
      format: AssistantAudioFormat(
        codec: payload.codec.lowercased(),
        sampleRate: payload.sampleRate,
        channels: payload.channels
      )
    )
  }

  public func appendPCMData(_ pcmData: Data, format incomingFormat: AssistantAudioFormat) throws {
    debugLog("[AssistantPlaybackEngine] appendPCMData: \(pcmData.count) bytes, format: \(incomingFormat.description)")
    debugLog("[AssistantPlaybackEngine] Current route: \(currentRouteDescription())")
    debugLog("[AssistantPlaybackEngine] Engine running: \(audioEngine.isRunning), ownsEngine: \(ownsEngine)")
    
    guard incomingFormat.codec == "pcm_s16le" else {
      throw AssistantPlaybackError.unsupportedCodec(incomingFormat.codec)
    }
    guard incomingFormat.sampleRate == Self.graphFormat.sampleRate else {
      throw AssistantPlaybackError.unsupportedSampleRate(incomingFormat.sampleRate)
    }
    guard incomingFormat.channels == 1 else {
      throw AssistantPlaybackError.unsupportedChannelCount(incomingFormat.channels)
    }
    guard pcmData.count % MemoryLayout<Int16>.size == 0 else {
      throw AssistantPlaybackError.invalidPCMByteCount(pcmData.count)
    }

    if let currentFormat, currentFormat != incomingFormat {
      throw AssistantPlaybackError.formatMismatch(expected: currentFormat, received: incomingFormat)
    }

    guard audioSession.category == .playAndRecord else {
      let expectedCategory = AVAudioSession.Category.playAndRecord.rawValue
      let actualCategory = audioSession.category.rawValue
      debugLog("[AssistantPlaybackEngine] appendPCMData aborted: AVAudioSession category is '\(actualCategory)', expected '\(expectedCategory)'")
      throw AssistantPlaybackError.invalidAudioSessionCategory(expected: expectedCategory, actual: actualCategory)
    }

    // Start the engine if needed before scheduling playback.
    try startEngineIfNeeded()

    let sampleCount = pcmData.count / MemoryLayout<Int16>.size
    let frameCount = AVAudioFrameCount(sampleCount)

    guard
      let audioFormat = avAudioFormat(for: incomingFormat),
      let buffer = AVAudioPCMBuffer(pcmFormat: audioFormat, frameCapacity: frameCount),
      let channelData = buffer.int16ChannelData
    else {
      throw AssistantPlaybackError.unableToAllocateBuffer
    }

    buffer.frameLength = frameCount
    pcmData.withUnsafeBytes { rawBuffer in
      guard let source = rawBuffer.baseAddress else { return }
      memcpy(channelData.pointee, source, pcmData.count)
    }

    let outputChannels = Int(playerNode.outputFormat(forBus: 0).channelCount)
    if outputChannels != Int(audioFormat.channelCount) {
      throw AssistantPlaybackError.outputChannelMismatch(
        expected: Int(audioFormat.channelCount),
        actual: outputChannels
      )
    }

    // Calculate buffer duration in milliseconds
    let bufferDurationMs = Double(frameCount) / Double(incomingFormat.sampleRate) * 1000.0
    let nowMs = nowMsProvider()

    // Check for stuck playback: buffers scheduled but never draining
    if queueState.shouldAttemptRecovery(
      nowMs: nowMs,
      thresholdMs: stuckDetectionThresholdMs,
      maxConsecutiveChecks: Self.maxStuckChecksBeforeRecovery
    ) {
      let timeSinceLastDrain = nowMs - queueState.lastBufferDrainedAtMs
      debugLog("[AssistantPlaybackEngine] Stuck playback detected: pendingCount=\(pendingBufferCount), timeSinceLastDrain=\(timeSinceLastDrain)ms, consecutiveChecks=\(queueState.consecutiveStuckChecks)")
      debugLog("[AssistantPlaybackEngine] Attempting stuck playback recovery")
      attemptPlaybackRecovery()
    }

    // Log backpressure state for observability but DO NOT drop audio chunks.
    // Dropping chunks causes truncated/missing audio on Bluetooth HFP where the hardware
    // drain rate is much slower than the server streaming rate.
    if pendingBufferDurationMs >= Self.maxPendingDurationMs || pendingBufferCount >= Self.maxPendingBuffers {
      debugLog("[AssistantPlaybackEngine] Backpressure: high queue depth, pendingBufferCount=\(pendingBufferCount), pendingDurationMs=\(Int(pendingBufferDurationMs)), chunkDurationMs=\(Int(bufferDurationMs))")
    }

    // IMPORTANT: Ensure engine is running and player node is connected BEFORE incrementing
    // pendingBufferCount and calling scheduleBuffer. If reconnection is needed after
    // scheduleBuffer is called, AVAudioEngine.connect() resets the player node and discards
    // the already-queued buffer without firing its completion callback — leaking the count.
    try ensureEngineRunning(context: "pre_play")

    // Check if player node is actually connected and attempt reconnection if needed
    if audioEngine.outputConnectionPoints(for: playerNode, outputBus: 0).isEmpty {
      debugLog("[AssistantPlaybackEngine] Player node disconnected, attempting reconnection")
      reconnectPlayerNode()

      // Verify reconnection succeeded
      guard !audioEngine.outputConnectionPoints(for: playerNode, outputBus: 0).isEmpty else {
        throw AssistantPlaybackError.engineStartFailed("Player node is disconnected from output graph.")
      }
      debugLog("[AssistantPlaybackEngine] Reconnection successful, continuing playback")
    }

    if !playerNode.isPlaying {
      debugLog("[AssistantPlaybackEngine] Starting player node")
      playerNode.play()
    }

    // Now it is safe to count and schedule: the graph is stable.
    queueState.recordScheduledBuffer(durationMs: bufferDurationMs, nowMs: nowMs)
    playerNode.scheduleBuffer(buffer) { [weak self, bufferDurationMs] in
      Task { @MainActor [weak self] in
        guard let self else { return }
        self.queueState.recordBufferDrained(durationMs: bufferDurationMs, nowMs: self.nowMsProvider())
      }
    }
    debugLog("[AssistantPlaybackEngine] Buffer scheduled, playerNode.isPlaying: \(playerNode.isPlaying)")
  }

  public func handlePlaybackControl(_ payload: PlaybackControlPayload) {
    switch payload.command {
    case .startResponse:
      startResponse()
    case .stopResponse:
      stopResponse()
    case .cancelResponse:
      cancelResponse()
    }
  }

  public func startResponse() {
    // IMPORTANT: Do NOT call playerNode.reset() or publishRouteUpdate() here.
    //
    // The original implementation used reset() + publishRouteUpdate(), but
    // publishRouteUpdate() can trigger reconnectPlayerNode() which calls
    // audioEngine.connect().  That reconnection drops the first scheduled
    // buffer — the comment on the old code warned about this very issue.
    //
    // By the time the backend sends `start_response`, the wake word handler
    // has already called cancelResponse() to clear any previous audio, and
    // the thinking chime has naturally finished.  All we need to do here is
    // reset the bookkeeping so backpressure tracking starts fresh.
    if pendingBufferCount > 0 {
      debugLog(
        "[AssistantPlaybackEngine] startResponse: resetting \(pendingBufferCount) pending buffers - possible orphaned completions from chime"
      )
    }

    queueState.resetForStartResponse(nowMs: nowMsProvider())
    debugLog("[AssistantPlaybackEngine] startResponse: counters reset, player node untouched")
  }

  public func stopResponse() {
    // `stop_response` indicates the server has finished streaming chunks.
    // Do not hard-stop here; stopping immediately can truncate queued audio
    // before it reaches the Bluetooth route.
  }

  public func cancelResponse() {
    playerNode.stop()
    playerNode.reset()
    queueState.resetForCancelResponse()
    debugLog("[AssistantPlaybackEngine] cancelResponse: flushed playback queue")
  }

  public func shutdown() {
    playerNode.stop()
    queueState.resetForCancelResponse()
    if isPlayerNodeAttached {
      audioEngine.detach(playerNode)
      isPlayerNodeAttached = false
      isPlayerNodeConnected = false
    }
    // Only stop the engine if we own it (created it internally)
    if ownsEngine {
      audioEngine.stop()
    }
    currentFormat = nil
  }

  public func currentRouteDescription() -> String {
    let outputs = audioSession.currentRoute.outputs.map(\.portType.rawValue)
    return outputs.joined(separator: ",")
  }

  private func connectPlayerNodeIfNeeded(for format: AssistantAudioFormat) throws {
    guard let avFormat = avAudioFormat(for: format) else {
      throw AssistantPlaybackError.unableToBuildAudioFormat
    }

    ensurePlayerNodeAttached()
    
    // Use flag as fast-path hint, but verify against actual engine state.
    // The flag can become stale after graph disruptions.
    let actuallyConnected = !audioEngine.outputConnectionPoints(for: playerNode, outputBus: 0).isEmpty
    if isPlayerNodeConnected && actuallyConnected {
      return
    }
    
    // If flag says connected but engine says not, correct the stale flag
    if isPlayerNodeConnected && !actuallyConnected {
      debugLog("[AssistantPlaybackEngine] Correcting stale isPlayerNodeConnected flag")
      isPlayerNodeConnected = false
    }
    
    audioEngine.connect(playerNode, to: audioEngine.mainMixerNode, format: avFormat)
    isPlayerNodeConnected = true
  }

  /// Attempts to reconnect the player node to the audio graph.
  /// Call this when the connection has been invalidated (e.g., background transitions, route changes).
  private func reconnectPlayerNode() {
    guard isPlayerNodeAttached else {
      debugLog("[AssistantPlaybackEngine] Cannot reconnect: player node not attached")
      return
    }

    debugLog("[AssistantPlaybackEngine] Reconnecting player node to output graph")

    // Mark as disconnected so connectPlayerNodeIfNeeded will re-establish the connection
    isPlayerNodeConnected = false

    // Try to reconnect with the current format
    let format = currentFormat ?? Self.graphFormat
    do {
      try connectPlayerNodeIfNeeded(for: format)
      debugLog("[AssistantPlaybackEngine] Player node reconnected successfully")
    } catch {
      debugLog("[AssistantPlaybackEngine] Failed to reconnect player node: \(error.localizedDescription)")
    }
  }

  /// Checks if the player node is actually connected to the output graph.
  /// The `isPlayerNodeConnected` flag can become stale after graph disruptions.
  private func isPlayerNodeActuallyConnected() -> Bool {
    guard isPlayerNodeAttached else { return false }
    return !audioEngine.outputConnectionPoints(for: playerNode, outputBus: 0).isEmpty
  }

  /// Call this when the app enters background to prepare for graph disruption.
  public func prepareForBackground() {
    debugLog("[AssistantPlaybackEngine] Preparing for background")
    // Mark connection as potentially stale - will be verified on next playback attempt
    isPlayerNodeConnected = false
  }

  /// Call this when the app returns to foreground to restore the audio graph.
  public func restoreFromBackground() {
    debugLog("[AssistantPlaybackEngine] Restoring from background")
    if !isPlayerNodeActuallyConnected() {
      reconnectPlayerNode()
    }
  }

  private func startEngineIfNeeded() throws {
    ensurePlayerNodeAttached()
    
    // Start the engine if it's not running, regardless of ownership.
    // When using a shared engine, the greeting audio may arrive before AudioCollectionManager.start()
    // completes. It's safe to start the shared engine from here since AVAudioEngine supports
    // concurrent input tap and output playback.
    if !audioEngine.isRunning {
      debugLog("[AssistantPlaybackEngine] Engine not running, starting it now (ownsEngine: \(ownsEngine))")
      do {
        audioEngine.prepare()
        try audioEngine.start()
        debugLog("[AssistantPlaybackEngine] Engine started successfully")
      } catch {
        debugLog("[AssistantPlaybackEngine] Failed to start engine: \(error.localizedDescription)")
        throw AssistantPlaybackError.engineStartFailed(error.localizedDescription)
      }
    }
  }

  private func ensureEngineRunning(context: String) throws {
    if !audioEngine.isRunning {
      debugLog("[AssistantPlaybackEngine] Engine not running (\(context)); preparing/start")
      audioEngine.prepare()
      do {
        try audioEngine.start()
      } catch {
        debugLog("[AssistantPlaybackEngine] Failed engine start (\(context)): \(error.localizedDescription)")
        throw AssistantPlaybackError.engineStartFailed(error.localizedDescription)
      }
    } else {
      // Graph changes on a shared engine can still leave the engine effectively not
      // render-ready; issue a start attempt as a no-op/recovery.
      do {
        try audioEngine.start()
      } catch {
        debugLog("[AssistantPlaybackEngine] Start reassert failed (\(context)): \(error.localizedDescription)")
      }
    }

    if !audioEngine.isRunning {
      throw AssistantPlaybackError.engineStartFailed("Engine is not running (\(context))")
    }
  }

  private func avAudioFormat(for format: AssistantAudioFormat) -> AVAudioFormat? {
    AVAudioFormat(
      commonFormat: .pcmFormatInt16,
      sampleRate: Double(format.sampleRate),
      channels: AVAudioChannelCount(format.channels),
      interleaved: false
    )
  }

  private func ensurePlayerNodeAttached() {
    guard !isPlayerNodeAttached else { return }
    audioEngine.attach(playerNode)
    isPlayerNodeAttached = true
  }

  private func publishRouteUpdate(notification: Notification? = nil) {
    let route = currentRouteDescription()
    onRouteChanged?(route)

    // Log detailed route change information for diagnostics
    logRouteChange(notification: notification)

    // Route changes can invalidate the audio graph connection
    // Check and reconnect if needed
    if isPlayerNodeAttached && !isPlayerNodeActuallyConnected() {
      debugLog("[AssistantPlaybackEngine] Route change invalidated player node connection, reconnecting")
      reconnectPlayerNode()
    }

    if !isBluetoothRouteActive(route: audioSession.currentRoute) {
      onRouteIssue?("Assistant playback route is not on glasses/Bluetooth output (\(route))")
    }
  }

  /// Logs detailed route change information for diagnostics.
  private func logRouteChange(notification: Notification?) {
    let route = audioSession.currentRoute
    let inputPorts = route.inputs.map { "\($0.portType.rawValue):\($0.portName)" }.joined(separator: ", ")
    let outputPorts = route.outputs.map { "\($0.portType.rawValue):\($0.portName)" }.joined(separator: ", ")
    let category = audioSession.category.rawValue
    let mode = audioSession.mode.rawValue

    var reasonStr = "unknown"
    if let userInfo = notification?.userInfo,
       let reasonRaw = userInfo[AVAudioSessionRouteChangeReasonKey] as? UInt,
       let reason = AVAudioSession.RouteChangeReason(rawValue: reasonRaw) {
      reasonStr = routeChangeReasonDescription(reason)
    }

    debugLog("[AssistantPlaybackEngine] audio.route_change: reason=\(reasonStr), category=\(category), mode=\(mode), inputs=[\(inputPorts)], outputs=[\(outputPorts)], pendingBufferCount=\(pendingBufferCount), pendingDurationMs=\(Int(pendingBufferDurationMs))")
  }

  private func routeChangeReasonDescription(_ reason: AVAudioSession.RouteChangeReason) -> String {
    switch reason {
    case .unknown: return "unknown"
    case .newDeviceAvailable: return "newDeviceAvailable"
    case .oldDeviceUnavailable: return "oldDeviceUnavailable"
    case .categoryChange: return "categoryChange"
    case .override: return "override"
    case .wakeFromSleep: return "wakeFromSleep"
    case .noSuitableRouteForCategory: return "noSuitableRouteForCategory"
    case .routeConfigurationChange: return "routeConfigurationChange"
    @unknown default: return "unknown(\(reason.rawValue))"
    }
  }

  private func isBluetoothRouteActive(route: AVAudioSessionRouteDescription) -> Bool {
    route.outputs.contains { output in
      output.portType == .bluetoothA2DP || output.portType == .bluetoothHFP || output.portType == .bluetoothLE
    }
  }

  private func handleInterruption(_ type: AVAudioSession.InterruptionType?) {
    guard let type else { return }
    switch type {
    case .began:
      // Interruption started - mark connection as potentially stale
      debugLog("[AssistantPlaybackEngine] Audio interruption began")
      isPlayerNodeConnected = false
    case .ended:
      // Interruption ended - attempt to restore the graph
      debugLog("[AssistantPlaybackEngine] Audio interruption ended, restoring graph")
      if !isPlayerNodeActuallyConnected() {
        reconnectPlayerNode()
      }
      publishRouteUpdate()
    @unknown default:
      break
    }
  }

  private nonisolated static func interruptionType(from notification: Notification) -> AVAudioSession.InterruptionType? {
    guard
      let rawType = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
      let type = AVAudioSession.InterruptionType(rawValue: rawType)
    else {
      return nil
    }
    return type
  }

  /// Returns current time in milliseconds since 1970.
  /// Logs detailed audio pipeline state for diagnostics.
  private func logAudioPipelineState(context: String) {
    let engineRunning = audioEngine.isRunning
    let playerPlaying = playerNode.isPlaying
    let playerNodeConnected = isPlayerNodeActuallyConnected()
    
    // Get format info from the audio chain
    let playerOutputFormat = playerNode.outputFormat(forBus: 0)
    let mixerInputFormat = audioEngine.mainMixerNode.inputFormat(forBus: 0)
    let outputNodeFormat = audioEngine.outputNode.outputFormat(forBus: 0)
    
    let route = audioSession.currentRoute
    let outputPorts = route.outputs.map { "\($0.portType.rawValue):\($0.portName)" }.joined(separator: ", ")
    
    debugLog("[AssistantPlaybackEngine] Pipeline state (\(context)): engineRunning=\(engineRunning), playerPlaying=\(playerPlaying), playerConnected=\(playerNodeConnected)")
    debugLog("[AssistantPlaybackEngine] Formats: playerOutput=\(playerOutputFormat.sampleRate)Hz/\(playerOutputFormat.channelCount)ch, mixerInput=\(mixerInputFormat.sampleRate)Hz/\(mixerInputFormat.channelCount)ch, outputNode=\(outputNodeFormat.sampleRate)Hz/\(outputNodeFormat.channelCount)ch")
    debugLog("[AssistantPlaybackEngine] Route outputs: [\(outputPorts)]")
  }

  /// Attempts to recover from stuck playback by restarting the audio graph.
  private func attemptPlaybackRecovery() {
    logAudioPipelineState(context: "pre_recovery")
    
    // Stop and reset the player node
    playerNode.stop()
    playerNode.reset()
    
    // Clear tracking state
    let previousPendingCount = pendingBufferCount
    let previousPendingDuration = pendingBufferDurationMs
    queueState.resetForRecovery(nowMs: nowMsProvider())
    
    debugLog("[AssistantPlaybackEngine] Recovery: cleared \(previousPendingCount) stuck buffers (~\(Int(previousPendingDuration))ms)")
    
    // Force reconnect the player node
    isPlayerNodeConnected = false
    do {
      try connectPlayerNodeIfNeeded(for: currentFormat ?? Self.graphFormat)
    } catch {
      debugLog("[AssistantPlaybackEngine] Recovery: failed to reconnect player node: \(error.localizedDescription)")
    }
    
    // Restart the engine if needed
    if !audioEngine.isRunning {
      debugLog("[AssistantPlaybackEngine] Recovery: engine stopped, attempting restart")
      audioEngine.prepare()
      do {
        try audioEngine.start()
        debugLog("[AssistantPlaybackEngine] Recovery: engine restarted successfully")
      } catch {
        debugLog("[AssistantPlaybackEngine] Recovery: failed to restart engine: \(error.localizedDescription)")
      }
    }
    
    logAudioPipelineState(context: "post_recovery")
  }

  private func debugLog(_ message: String) {
#if DEBUG
    Self.logger.debug("\(message, privacy: .public)")
#endif
  }
}
