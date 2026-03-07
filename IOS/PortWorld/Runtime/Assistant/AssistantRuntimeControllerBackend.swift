import Foundation

extension AssistantRuntimeController {
  func bindBackendEvents() {
    debugLog("Binding backend event handler")
    Task { [weak self] in
      await self?.backendSessionClient.setEventHandler { [weak self] envelope in
        Task { @MainActor [weak self] in
          guard let self else { return }
          self.debugLog("Consuming backend event#\(envelope.id) \(self.describeBackendEvent(envelope.event))")
          await self.handleBackendEvent(envelope)
        }
      }
    }
  }

  func handleBackendEvent(_ envelope: BackendSessionClient.EventEnvelope) async {
    switch envelope.event {
    case .stateChanged(let state):
      snapshot.backendStatusText = state.rawValue
      snapshot.transportStatusText = state.rawValue

    case .sessionReady:
      debugLog("Received backend session.state active event#\(envelope.id)")
      snapshot.transportStatusText = "ready"
      markConversationReady(source: "session_state_active")

    case .uplinkAcknowledged(let payload):
      firstUplinkAckReceived = true
      snapshot.uplinkStatusText = "ack frames=\(payload.framesReceived) bytes=\(payload.bytesReceived)"
      debugLog("Received uplink ack event#\(envelope.id) frames=\(payload.framesReceived) bytes=\(payload.bytesReceived)")

    case .serverAudio(let data):
      do {
        debugLog("Received server audio event#\(envelope.id) bytes=\(data.count)")
        debugLog("Calling appendAssistantPCMData for event#\(envelope.id)")
        try phoneAudioIO.appendAssistantPCMData(data)
        debugLog("appendAssistantPCMData completed for event#\(envelope.id) route=\(phoneAudioIO.playbackRouteDescription())")
        let diagnostics = await backendSessionClient.diagnosticsSnapshot()
        snapshot.playbackStatusText = "scheduled frames=\(diagnostics.inboundServerAudioFrameCount) bytes=\(diagnostics.inboundServerAudioBytes)"
        snapshot.playbackRouteText = phoneAudioIO.playbackRouteDescription()
      } catch {
        snapshot.playbackStatusText = "playback_failed"
        snapshot.errorText = "Failed to play assistant audio: \(error.localizedDescription)"
      }

    case .playbackControl(let payload):
      debugLog("Received playback control event#\(envelope.id) command=\(payload.command.rawValue)")
      snapshot.playbackStatusText = payload.command.rawValue
      phoneAudioIO.handlePlaybackControl(payload)

    case .closed:
      if isResettingConversationToArmedState {
        break
      }
      if snapshot.assistantRuntimeState == .activeConversation || snapshot.assistantRuntimeState == .connectingConversation {
        await resetConversationToArmedState(reason: "Connection closed. Listening for wake phrase again.")
      }

    case .error(let message):
      if isResettingConversationToArmedState, isExpectedDisconnectError(message) {
        debugLog("Ignoring expected backend disconnect error during reset: \(message)")
        break
      }
      snapshot.errorText = message
      if snapshot.assistantRuntimeState == .connectingConversation || snapshot.assistantRuntimeState == .activeConversation {
        await resetConversationToArmedState(reason: "Conversation failed. Listening for wake phrase again.")
      }
    }

    await refreshSubsystemStatus()
    publishSnapshot()
  }

  func isExpectedDisconnectError(_ message: String) -> Bool {
    let normalized = message.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    return normalized.contains("socket is not connected")
  }

  func describeBackendEvent(_ event: BackendSessionClient.Event) -> String {
    switch event {
    case .stateChanged(let state):
      return "state_changed=\(state.rawValue)"
    case .sessionReady:
      return "session_ready"
    case .uplinkAcknowledged(let payload):
      return "uplink_ack frames=\(payload.framesReceived) bytes=\(payload.bytesReceived)"
    case .serverAudio(let data):
      return "server_audio bytes=\(data.count)"
    case .playbackControl(let payload):
      return "playback_control command=\(payload.command.rawValue)"
    case .closed:
      return "closed"
    case .error(let message):
      return "error=\(message)"
    }
  }
}
