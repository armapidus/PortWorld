import Foundation

enum SessionState: String, Codable {
  case idle
  case connecting
  case active
  case streaming
  case reconnecting
  case disconnecting
  case ended
  case failed
}

enum AssistantRuntimeState: String, Codable {
  case inactive
  case armedListening = "armed_listening"
  case connectingConversation = "connecting_conversation"
  case activeConversation = "active_conversation"
  case deactivating
}

enum WakeWordMode: String, Codable {
  case manualOnly = "manual_only"
  case onDevicePreferred = "on_device_preferred"
}

struct AssistantAudioChunkPayload: Codable {
  let responseID: String
  let chunkID: String
  let codec: String
  let sampleRate: Int
  let channels: Int
  let durationMs: Int
  let isLast: Bool
  let bytesB64: String

  private enum CodingKeys: String, CodingKey {
    case responseID = "response_id"
    case chunkID = "chunk_id"
    case codec
    case sampleRate = "sample_rate"
    case channels
    case durationMs = "duration_ms"
    case isLast = "is_last"
    case bytesB64 = "bytes_b64"
  }
}

enum PlaybackControlCommand: String, Codable {
  case startResponse = "start_response"
  case stopResponse = "stop_response"
  case cancelResponse = "cancel_response"
}

struct PlaybackControlPayload: Codable {
  let command: PlaybackControlCommand
  let responseID: String?

  private enum CodingKeys: String, CodingKey {
    case command
    case responseID = "response_id"
  }
}

struct RealtimeUplinkAckPayload: Codable {
  let framesReceived: Int
  let bytesReceived: Int
  let probeAcknowledged: Bool?

  private enum CodingKeys: String, CodingKey {
    case framesReceived = "frames_received"
    case bytesReceived = "bytes_received"
    case probeAcknowledged = "probe_acknowledged"
  }
}

struct RuntimeErrorPayload: Codable {
  let code: String
  let retriable: Bool
  let message: String
}

struct SessionStatePayload: Codable {
  let state: SessionState
  let detail: String?
}

struct EmptyPayload: Codable {}

struct SessionActivatePayload: Codable {
  struct SessionInfo: Codable {
    let type: String
  }

  struct ClientAudioFormat: Codable {
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

struct WakewordDetectedPayload: Codable {
  let wakePhrase: String
  let engine: String
  let confidence: Double?

  private enum CodingKeys: String, CodingKey {
    case wakePhrase = "wake_phrase"
    case engine
    case confidence
  }
}

struct WSMessageEnvelope<Payload> {
  let type: String
  let sessionID: String
  let seq: Int
  let tsMs: Int64
  let payload: Payload

  init(
    type: String,
    sessionID: String,
    seq: Int,
    tsMs: Int64 = Int64(Date().timeIntervalSince1970 * 1000),
    payload: Payload
  ) {
    self.type = type
    self.sessionID = sessionID
    self.seq = seq
    self.tsMs = tsMs
    self.payload = payload
  }

  private enum CodingKeys: String, CodingKey {
    case type
    case sessionID = "session_id"
    case seq
    case tsMs = "ts_ms"
    case payload
  }
}

extension WSMessageEnvelope: Encodable where Payload: Encodable {}
extension WSMessageEnvelope: Decodable where Payload: Decodable {}

struct WSRawMessageEnvelope: Codable {
  let type: String
  let sessionID: String
  let seq: Int
  let tsMs: Int64
  let payload: JSONValue

  private enum CodingKeys: String, CodingKey {
    case type
    case sessionID = "session_id"
    case seq
    case tsMs = "ts_ms"
    case payload
  }
}

enum WSOutboundType: String, Codable {
  case sessionActivate = "session.activate"
  case sessionDeactivate = "session.deactivate"
  case sessionEndTurn = "session.end_turn"
  case wakewordDetected = "wakeword.detected"
  case error
}

enum WSInboundType: String, Codable {
  case sessionState = "session.state"
  case assistantPlaybackControl = "assistant.playback.control"
  case error
}

enum WSMessageCodec {
  static func decodeRawEnvelope(from data: Data, decoder: JSONDecoder = JSONDecoder()) throws -> WSRawMessageEnvelope {
    try decoder.decode(WSRawMessageEnvelope.self, from: data)
  }

  static func encodeEnvelope<Payload: Encodable>(
    _ envelope: WSMessageEnvelope<Payload>,
    encoder: JSONEncoder = JSONEncoder()
  ) throws -> Data {
    try encoder.encode(envelope)
  }
}

enum JSONValue: Codable, Equatable {
  case string(String)
  case number(Double)
  case bool(Bool)
  case object([String: JSONValue])
  case array([JSONValue])
  case null

  init(from decoder: Decoder) throws {
    let container = try decoder.singleValueContainer()

    if container.decodeNil() {
      self = .null
      return
    }
    if let boolValue = try? container.decode(Bool.self) {
      self = .bool(boolValue)
      return
    }
    if let intValue = try? container.decode(Int.self) {
      self = .number(Double(intValue))
      return
    }
    if let doubleValue = try? container.decode(Double.self) {
      self = .number(doubleValue)
      return
    }
    if let stringValue = try? container.decode(String.self) {
      self = .string(stringValue)
      return
    }
    if let objectValue = try? container.decode([String: JSONValue].self) {
      self = .object(objectValue)
      return
    }
    if let arrayValue = try? container.decode([JSONValue].self) {
      self = .array(arrayValue)
      return
    }

    throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value")
  }

  func encode(to encoder: Encoder) throws {
    var container = encoder.singleValueContainer()

    switch self {
    case .string(let value):
      try container.encode(value)
    case .number(let value):
      try container.encode(value)
    case .bool(let value):
      try container.encode(value)
    case .object(let value):
      try container.encode(value)
    case .array(let value):
      try container.encode(value)
    case .null:
      try container.encodeNil()
    }
  }
}
