import Foundation

enum WavFileWriterError: Error {
    case invalidConfiguration
}

struct WavFileWriter {
    static func writePCM16(
        samples: Data,
        sampleRate: Int,
        channels: Int,
        to url: URL
    ) throws -> Int64 {
        guard sampleRate > 0, channels > 0 else {
            throw WavFileWriterError.invalidConfiguration
        }

        let bitsPerSample: UInt16 = 16
        let bytesPerSample = Int(bitsPerSample / 8)
        let blockAlign = UInt16(channels * bytesPerSample)
        let byteRate = UInt32(sampleRate) * UInt32(blockAlign)
        let dataChunkSize = UInt32(samples.count)
        let riffChunkSize = UInt32(36) + dataChunkSize

        var wav = Data(capacity: 44 + samples.count)
        wav.append(Data("RIFF".utf8))
        wav.appendLE(riffChunkSize)
        wav.append(Data("WAVE".utf8))
        wav.append(Data("fmt ".utf8))
        wav.appendLE(UInt32(16))
        wav.appendLE(UInt16(1))
        wav.appendLE(UInt16(channels))
        wav.appendLE(UInt32(sampleRate))
        wav.appendLE(byteRate)
        wav.appendLE(blockAlign)
        wav.appendLE(bitsPerSample)
        wav.append(Data("data".utf8))
        wav.appendLE(dataChunkSize)
        wav.append(samples)

        try wav.write(to: url, options: .atomic)
        return Int64(wav.count)
    }
}

private extension Data {
    mutating func appendLE<T: FixedWidthInteger>(_ value: T) {
        var littleEndian = value.littleEndian
        Swift.withUnsafeBytes(of: &littleEndian) { rawBuffer in
            append(rawBuffer.bindMemory(to: UInt8.self))
        }
    }
}
