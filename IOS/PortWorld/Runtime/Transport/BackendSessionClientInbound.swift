import Foundation

extension BackendSessionClient {
  func runReceiveLoop() async {
    while !Task.isCancelled {
      guard let webSocketTask else { return }

      do {
        let message = try await webSocketTask.receive()
        switch message {
        case .string(let text):
          guard let data = text.data(using: .utf8) else { continue }
          try await handleControlMessage(data)
        case .data(let data):
          try await handleBinaryMessage(data)
        @unknown default:
          yieldEvent(.error("Unsupported websocket message kind."))
        }
      } catch is CancellationError {
        return
      } catch {
        if shouldIgnoreReceiveLoopError(error) {
          return
        }
        yieldEvent(.error(error.localizedDescription))
        return
      }
    }
  }

  func shouldIgnoreReceiveLoopError(_ error: Error) -> Bool {
    guard isLocallyDisconnecting else { return false }
    let normalized = error.localizedDescription.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    return normalized.contains("socket is not connected")
  }

  func handleControlMessage(_ data: Data) async throws {
    let rawEnvelope = try PhoneOnlyWSMessageCodec.decodeRawEnvelopeType(from: data)
    debugLog("Inbound control type=\(rawEnvelope)")

    switch rawEnvelope {
    case PhoneOnlyWSInboundType.sessionState.rawValue:
      let envelope = try PhoneOnlyWSMessageCodec.decodeEnvelope(PhoneOnlySessionStatePayload.self, from: data)
      debugLog("Inbound session.state=\(envelope.payload.state.rawValue)")
      if envelope.payload.state == .active {
        yieldEvent(.sessionReady)
      }
    case PhoneOnlyWSInboundType.transportUplinkAcknowledged.rawValue:
      let envelope = try PhoneOnlyWSMessageCodec.decodeEnvelope(PhoneOnlyRealtimeUplinkAckPayload.self, from: data)
      debugLog("Inbound transport.uplink.ack frames=\(envelope.payload.framesReceived) bytes=\(envelope.payload.bytesReceived)")
      yieldEvent(.uplinkAcknowledged(envelope.payload))
    case PhoneOnlyWSInboundType.assistantPlaybackControl.rawValue:
      let envelope = try PhoneOnlyWSMessageCodec.decodeEnvelope(PhoneOnlyPlaybackControlPayload.self, from: data)
      lastPlaybackControlCommand = envelope.payload.command.rawValue
      debugLog("Inbound assistant.playback.control command=\(envelope.payload.command.rawValue)")
      yieldEvent(.playbackControl(envelope.payload))
    case PhoneOnlyWSInboundType.error.rawValue:
      let envelope = try PhoneOnlyWSMessageCodec.decodeEnvelope(PhoneOnlyRuntimeErrorPayload.self, from: data)
      debugLog("Inbound error code=\(envelope.payload.code) message=\(envelope.payload.message)")
      yieldEvent(.error(envelope.payload.message))
    default:
      break
    }
  }

  func handleBinaryMessage(_ data: Data) async throws {
    let frame = try PhoneOnlyBinaryFrameCodec.decode(data)
    guard frame.frameType == .serverAudio else { return }
    inboundServerAudioFrameCount += 1
    inboundServerAudioBytes += frame.payload.count
    lastInboundServerAudioBytes = frame.payload.count
    if loggedFirstServerAudioFrame == false {
      loggedFirstServerAudioFrame = true
      debugLog("Inbound first server audio frame bytes=\(frame.payload.count) timestamp=\(frame.timestampMs)")
    }
    yieldEvent(.serverAudio(frame.payload))
  }
}
