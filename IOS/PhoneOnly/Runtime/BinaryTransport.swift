import Foundation

enum TransportFrameType: UInt8, Sendable {
  case clientAudio = 0x01
  case serverAudio = 0x02
}

struct TransportBinaryFrame: Sendable, Equatable {
  let frameType: TransportFrameType
  let timestampMs: Int64
  let payload: Data
}

enum TransportBinaryFrameCodec {
  enum DecodeError: Error, Sendable, Equatable {
    case frameTooShort(expectedMinimum: Int, actual: Int)
    case unsupportedFrameType(UInt8)
  }

  private static let headerSize = 9

  static func encode(_ frame: TransportBinaryFrame) -> Data {
    var data = Data(capacity: headerSize + frame.payload.count)
    data.append(frame.frameType.rawValue)

    var timestampLE = UInt64(bitPattern: frame.timestampMs).littleEndian
    withUnsafeBytes(of: &timestampLE) { bytes in
      data.append(contentsOf: bytes)
    }

    data.append(frame.payload)
    return data
  }

  static func decode(_ data: Data) throws -> TransportBinaryFrame {
    guard data.count >= headerSize else {
      throw DecodeError.frameTooShort(expectedMinimum: headerSize, actual: data.count)
    }

    let frameTypeByte = data[data.startIndex]
    guard let frameType = TransportFrameType(rawValue: frameTypeByte) else {
      throw DecodeError.unsupportedFrameType(frameTypeByte)
    }

    let timestampStart = data.index(after: data.startIndex)
    let payloadStart = data.index(data.startIndex, offsetBy: headerSize)

    var rawTimestamp: UInt64 = 0
    for (shift, byte) in data[timestampStart..<payloadStart].enumerated() {
      rawTimestamp |= UInt64(byte) << UInt64(shift * 8)
    }

    return TransportBinaryFrame(
      frameType: frameType,
      timestampMs: Int64(bitPattern: rawTimestamp),
      payload: Data(data[payloadStart..<data.endIndex])
    )
  }
}
