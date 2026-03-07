// Conversation flow and realtime audio uplink handling for the phone-only assistant.
import Foundation

extension AssistantRuntimeController {
  func endConversation() async {
    guard status.assistantRuntimeState == .activeConversation || status.assistantRuntimeState == .connectingConversation else { return }
    do {
      try await backendSessionClient.sendEndTurn()
    } catch {
      status.errorText = "Failed to send end-turn: \(error.localizedDescription)"
    }
    await resetConversationToArmedState(reason: "Conversation ended. Listening for wake phrase again.")
  }

  func startConversation(from event: WakeWordDetectionEvent) async {
    guard status.assistantRuntimeState == .armedListening else { return }

    wakeWarmupTask?.cancel()
    wakeWarmupTask = nil
    wakeListeningGeneration += 1
    activeSessionID = "sess_\(UUID().uuidString)"
    backendReady = false
    firstUplinkAckReceived = false
    isSuppressingRealtimeUplinkForPlayback = false
    awaitingFirstWakePCMFrame = false
    activeConversationStartedAtMs = nil
    status.errorText = ""
    status.assistantRuntimeState = .connectingConversation
    status.sessionID = activeSessionID ?? "-"
    status.transportStatusText = "connecting"
    status.uplinkStatusText = "waiting_for_backend_ready"
    status.playbackStatusText = "waiting_for_server_response"
    status.infoText = "Wake detected. Opening backend conversation."
    publishStatus()

    guard let activeSessionID else { return }
    await backendSessionClient.connect(sessionID: activeSessionID)

    do {
      try await backendSessionClient.sendSessionActivate()
      try await backendSessionClient.sendWakewordDetected(event)
      debugLog("Conversation control messages sent; enabling realtime uplink for session \(activeSessionID)")
      markConversationReady(source: "control_messages_sent")
    } catch {
      status.errorText = "Failed to start backend conversation: \(error.localizedDescription)"
      await resetConversationToArmedState(reason: "Listening for wake phrase again.")
      return
    }
  }

  func handleRealtimePCMFrame(_ payload: Data, timestampMs: Int64) async {
    switch status.assistantRuntimeState {
    case .connectingConversation:
      bufferRealtimeFrame(payload, timestampMs: timestampMs)
      return
    case .activeConversation:
      break
    case .inactive, .armedListening, .deactivating:
      return
    }

    guard backendReady else {
      bufferRealtimeFrame(payload, timestampMs: timestampMs)
      return
    }

    if phoneAudioIO.shouldSuppressRealtimeUplink() {
      if isSuppressingRealtimeUplinkForPlayback == false {
        isSuppressingRealtimeUplinkForPlayback = true
        status.uplinkStatusText = "suppressed_during_playback"
        debugLog("Suppressing realtime uplink while assistant playback is active")
        publishStatus()
      }
      return
    }

    if isSuppressingRealtimeUplinkForPlayback {
      isSuppressingRealtimeUplinkForPlayback = false
      debugLog("Resuming realtime uplink after assistant playback")
    }

    do {
      if pendingRealtimeFrames.isEmpty == false {
        await flushPendingRealtimeFrames()
      }
      if firstUplinkAckReceived == false, status.uplinkStatusText == "streaming_live_audio" {
        status.uplinkStatusText = "sending_first_live_audio"
        debugLog("Sending first live client audio frame timestamp=\(timestampMs)")
      }
      try await backendSessionClient.sendAudioFrame(payload, timestampMs: timestampMs)
      let diagnostics = await backendSessionClient.diagnosticsSnapshot()
      status.uplinkStatusText = "binary_sent=\(diagnostics.binarySendSuccessCount) last=\(diagnostics.lastBinaryFirstByteHex)"
      if diagnostics.binarySendSuccessCount == 1 {
        debugLog("First binary client audio send completed bytes=\(diagnostics.lastOutboundBytes)")
      }
    } catch {
      status.errorText = "Failed to send client audio: \(error.localizedDescription)"
    }
    publishStatus()
  }

  func handleSleepDetected(_ event: WakeWordDetectionEvent) async {
    guard status.assistantRuntimeState == .activeConversation else {
      return
    }

    guard let activeConversationStartedAtMs else {
      debugLog("Ignoring sleep phrase because active conversation start time is unavailable")
      return
    }

    let activeDurationMs = max(0, event.timestampMs - activeConversationStartedAtMs)
    guard activeDurationMs >= config.sleepWordMinActiveStreamMs else {
      debugLog(
        "Ignoring sleep phrase because active conversation duration \(activeDurationMs)ms is below threshold \(config.sleepWordMinActiveStreamMs)ms"
      )
      return
    }

    debugLog("Accepting sleep phrase after active duration \(activeDurationMs)ms")
    await endConversation()
  }

  func resetConversationToArmedState(reason: String) async {
    guard isResettingConversationToArmedState == false else {
      debugLog("Reset to armed state already in progress")
      return
    }

    isResettingConversationToArmedState = true
    phoneAudioIO.cancelPlayback()
    activeSessionID = nil
    backendReady = false
    firstUplinkAckReceived = false
    isSuppressingRealtimeUplinkForPlayback = false
    activeConversationStartedAtMs = nil
    awaitingFirstWakePCMFrame = true
    pendingRealtimeFrames.removeAll(keepingCapacity: false)
    wakeListeningGeneration += 1
    let generation = wakeListeningGeneration
    status.assistantRuntimeState = .armedListening
    status.sessionID = "-"
    status.transportStatusText = "idle"
    status.uplinkStatusText = "armed_waiting_for_wake"
    status.playbackStatusText = "armed_waiting_for_response"
    status.infoText = "Warming up wake detection."
    await backendSessionClient.disconnect(sendDeactivate: false)
    await refreshSubsystemStatus()
    publishStatus()
    scheduleWakeListeningStart(generation: generation, readyMessage: reason)
    isResettingConversationToArmedState = false
  }

  func markConversationReady(source: String) {
    backendReady = true
    activeConversationStartedAtMs = Clocks.nowMs()
    awaitingFirstWakePCMFrame = false
    status.assistantRuntimeState = .activeConversation
    status.uplinkStatusText = firstUplinkAckReceived ? status.uplinkStatusText : "streaming_live_audio"
    status.infoText = "Conversation active."
    debugLog("Conversation active via \(source); pendingFrames=\(pendingRealtimeFrames.count)")
  }

  func bufferRealtimeFrame(_ payload: Data, timestampMs: Int64) {
    pendingRealtimeFrames.append(PendingRealtimeFrame(payload: payload, timestampMs: timestampMs))
    if pendingRealtimeFrames.count > maxPendingRealtimeFrames {
      pendingRealtimeFrames.removeFirst(pendingRealtimeFrames.count - maxPendingRealtimeFrames)
    }
  }

  func flushPendingRealtimeFrames() async {
    guard backendReady, pendingRealtimeFrames.isEmpty == false else { return }
    let frames = pendingRealtimeFrames
    pendingRealtimeFrames.removeAll(keepingCapacity: true)
    debugLog("Flushing \(frames.count) buffered realtime frames")
    for frame in frames {
      do {
        try await backendSessionClient.sendAudioFrame(frame.payload, timestampMs: frame.timestampMs)
      } catch {
        status.errorText = "Failed to flush client audio: \(error.localizedDescription)"
        return
      }
    }
    let diagnostics = await backendSessionClient.diagnosticsSnapshot()
    status.uplinkStatusText = "binary_sent=\(diagnostics.binarySendSuccessCount) last=\(diagnostics.lastBinaryFirstByteHex)"
  }
}
