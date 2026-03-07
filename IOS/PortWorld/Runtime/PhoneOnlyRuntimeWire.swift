// Phone-only websocket and binary framing types for the active assistant runtime.
import Foundation

enum PhoneOnlySessionState: String, Codable, Sendable {
  case idle
  case connecting
  case active
  case streaming
  case reconnecting
  case disconnecting
  case ended
  case failed
}

enum PhoneOnlyPlaybackControlCommand: String, Codable, Sendable {
  case startResponse = "start_response"
  case stopResponse = "stop_response"
  case cancelResponse = "cancel_response"
}

nonisolated struct PhoneOnlyPlaybackControlPayload: Codable, Sendable {
  let command: PhoneOnlyPlaybackControlCommand
  let responseID: String?

  init(command: PhoneOnlyPlaybackControlCommand, responseID: String? = nil) {
    self.command = command
    self.responseID = responseID
  }

  private enum CodingKeys: String, CodingKey {
    case command
    case responseID = "response_id"
  }
}

nonisolated struct PhoneOnlyRealtimeUplinkAckPayload: Codable, Sendable {
  let framesReceived: Int
  let bytesReceived: Int
  let probeAcknowledged: Bool?

  private enum CodingKeys: String, CodingKey {
    case framesReceived = "frames_received"
    case bytesReceived = "bytes_received"
    case probeAcknowledged = "probe_acknowledged"
  }
}

nonisolated struct PhoneOnlyRuntimeErrorPayload: Codable, Sendable {
  let code: String
  let retriable: Bool
  let message: String
}

nonisolated struct PhoneOnlySessionStatePayload: Codable, Sendable {
  let state: PhoneOnlySessionState
  let detail: String?
}

nonisolated struct PhoneOnlyEmptyPayload: Codable, Sendable {}

nonisolated struct PhoneOnlySessionActivatePayload: Codable, Sendable {
  nonisolated struct SessionInfo: Codable, Sendable {
    let type: String
  }

  nonisolated struct ClientAudioFormat: Codable, Sendable {
    let encoding: String
    let channels: Int
    let sampleRate: Int

    private enum CodingKeys: String, CodingKey {
      case encoding
      case channels
      case sampleRate = "sample_rate"
    }
  }

  let session: SessionInfo
  let audioFormat: ClientAudioFormat

  private enum CodingKeys: String, CodingKey {
    case session
    case audioFormat = "audio_format"
  }
}

nonisolated struct PhoneOnlyWakewordDetectedPayload: Codable, Sendable {
  let wakePhrase: String
  let engine: String
  let confidence: Double?

  private enum CodingKeys: String, CodingKey {
    case wakePhrase = "wake_phrase"
    case engine
    case confidence
  }
}

@preconcurrency nonisolated struct PhoneOnlyWSControlEnvelope<Payload> {
  let type: String
  let sessionID: String
  let seq: Int
  let tsMs: Int64
  let payload: Payload

  init(type: String, sessionID: String, seq: Int, tsMs: Int64 = Int64(Date().timeIntervalSince1970 * 1000), payload: Payload) {
    self.type = type
    self.sessionID = sessionID
    self.seq = seq
    self.tsMs = tsMs
    self.payload = payload
  }
}

extension PhoneOnlyWSControlEnvelope: Sendable where Payload: Sendable {}

private nonisolated struct PhoneOnlyWSRawEnvelopeHeader: Decodable, Sendable {
  let type: String
}

enum PhoneOnlyWSOutboundType: String, Codable, Sendable {
  case sessionActivate = "session.activate"
  case sessionDeactivate = "session.deactivate"
  case sessionEndTurn = "session.end_turn"
  case wakewordDetected = "wakeword.detected"
}

enum PhoneOnlyWSInboundType: String, Codable, Sendable {
  case sessionState = "session.state"
  case transportUplinkAcknowledged = "transport.uplink.ack"
  case assistantPlaybackControl = "assistant.playback.control"
  case error
}

@preconcurrency enum PhoneOnlyWSMessageCodec {
  nonisolated static func decodeRawEnvelopeType(from data: Data, decoder: JSONDecoder = JSONDecoder()) throws -> String {
    try decoder.decode(PhoneOnlyWSRawEnvelopeHeader.self, from: data).type
  }

  nonisolated static func decodeEnvelope<Payload: Decodable>(
    _ payloadType: Payload.Type,
    from data: Data,
    decoder: JSONDecoder = JSONDecoder()
  ) throws -> PhoneOnlyWSControlEnvelope<Payload> {
    guard
      let jsonObject = try JSONSerialization.jsonObject(with: data) as? [String: Any],
      let type = jsonObject["type"] as? String,
      let sessionID = jsonObject["session_id"] as? String,
      let seq = jsonObject["seq"] as? Int,
      let tsValue = jsonObject["ts_ms"]
    else {
      throw PhoneOnlyTransportError.decoding("Malformed websocket control envelope.")
    }

    let tsMs: Int64
    if let integer = tsValue as? Int64 {
      tsMs = integer
    } else if let integer = tsValue as? Int {
      tsMs = Int64(integer)
    } else if let number = tsValue as? NSNumber {
      tsMs = number.int64Value
    } else {
      throw PhoneOnlyTransportError.decoding("Invalid websocket envelope timestamp.")
    }

    let payloadObject = jsonObject["payload"] ?? [:]
    guard JSONSerialization.isValidJSONObject(payloadObject) else {
      throw PhoneOnlyTransportError.decoding("Invalid websocket envelope payload object.")
    }

    let payloadData = try JSONSerialization.data(withJSONObject: payloadObject)
    let payload = try decoder.decode(payloadType, from: payloadData)
    return PhoneOnlyWSControlEnvelope(type: type, sessionID: sessionID, seq: seq, tsMs: tsMs, payload: payload)
  }

  nonisolated static func encodeEnvelope<Payload: Encodable>(
    _ envelope: PhoneOnlyWSControlEnvelope<Payload>,
    encoder: JSONEncoder = JSONEncoder()
  ) throws -> Data {
    let payloadData = try encoder.encode(envelope.payload)
    let payloadObject = try JSONSerialization.jsonObject(with: payloadData)
    let envelopeObject: [String: Any] = [
      "type": envelope.type,
      "session_id": envelope.sessionID,
      "seq": envelope.seq,
      "ts_ms": envelope.tsMs,
      "payload": payloadObject,
    ]
    return try JSONSerialization.data(withJSONObject: envelopeObject)
  }
}

enum PhoneOnlyBinaryFrameType: UInt8, Sendable {
  case clientAudio = 0x01
  case serverAudio = 0x02
}

nonisolated struct PhoneOnlyBinaryFrame: Sendable, Equatable {
  let frameType: PhoneOnlyBinaryFrameType
  let timestampMs: Int64
  let payload: Data
}

@preconcurrency enum PhoneOnlyBinaryFrameCodec {
  enum DecodeError: Error, LocalizedError, Sendable {
    case frameTooShort(expectedMinimum: Int, actual: Int)
    case unsupportedFrameType(UInt8)

    nonisolated var errorDescription: String? {
      switch self {
      case .frameTooShort(let expectedMinimum, let actual):
        return "Binary frame too short. Expected at least \(expectedMinimum) bytes, got \(actual)."
      case .unsupportedFrameType(let rawType):
        return "Unsupported binary frame type 0x\(String(format: "%02x", rawType))."
      }
    }
  }

  private nonisolated static let headerSize = 9

  nonisolated static func encode(_ frame: PhoneOnlyBinaryFrame) -> Data {
    var data = Data(capacity: headerSize + frame.payload.count)
    data.append(frame.frameType.rawValue)

    var timestampLE = UInt64(bitPattern: frame.timestampMs).littleEndian
    withUnsafeBytes(of: &timestampLE) { bytes in
      data.append(contentsOf: bytes)
    }

    data.append(frame.payload)
    return data
  }

  nonisolated static func decode(_ data: Data) throws -> PhoneOnlyBinaryFrame {
    guard data.count >= headerSize else {
      throw DecodeError.frameTooShort(expectedMinimum: headerSize, actual: data.count)
    }

    let headerStart = data.startIndex
    let timestampStart = data.index(after: headerStart)
    let payloadStart = data.index(headerStart, offsetBy: headerSize)

    let rawType = data[headerStart]
    guard let frameType = PhoneOnlyBinaryFrameType(rawValue: rawType) else {
      throw DecodeError.unsupportedFrameType(rawType)
    }

    var rawTimestamp: UInt64 = 0
    for (shift, byte) in data[timestampStart..<payloadStart].enumerated() {
      rawTimestamp |= UInt64(byte) << UInt64(shift * 8)
    }

    return PhoneOnlyBinaryFrame(
      frameType: frameType,
      timestampMs: Int64(bitPattern: rawTimestamp),
      payload: Data(data[payloadStart..<data.endIndex])
    )
  }
}
