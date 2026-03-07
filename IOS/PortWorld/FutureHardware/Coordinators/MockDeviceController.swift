@preconcurrency import AVFoundation
import CoreGraphics
import CoreMedia
import CoreVideo
import Foundation
import ImageIO
import UniformTypeIdentifiers

#if DEBUG
import MWDATMockDevice

private enum MockMediaDefaults {
  static let mediaDirectoryName = "portworld-mock-device"
  static let imageFileName = "default-captured-image.jpg"
  static let videoFileName = "default-camera-feed.mov"
  static let videoWidth = 320
  static let videoHeight = 240
  static let videoFPS: Int32 = 24
  static let videoFrameCount = 24
}
#endif

@MainActor
final class MockDeviceController {
  enum MockDeviceControllerError: LocalizedError {
    case failedToCreateTempDirectory(String)
    case failedToGenerateDefaultImage(String)
    case failedToWriteDefaultImage(String)
    case pairedDeviceIsNotRaybanMeta
    case failedToCreateVideoWriter(String)
    case videoEncodingNotSupported(String)
    case failedToStartVideoWriter(String)
    case failedToCreatePixelBuffer(String)
    case failedToAppendVideoFrame(String)
    case failedToFinishVideoWriter(String)
    case failedToGenerateVideo(String)

    var errorDescription: String? {
      switch self {
      case let .failedToCreateTempDirectory(message):
        return "Failed to create mock media temp directory: \(message)"
      case let .failedToGenerateDefaultImage(message):
        return "Failed to generate default mock image: \(message)"
      case let .failedToWriteDefaultImage(message):
        return "Failed to write default mock image: \(message)"
      case .pairedDeviceIsNotRaybanMeta:
        return "The paired mock device is not a Ray-Ban Meta mock device."
      case let .failedToCreateVideoWriter(message):
        return "Failed to create mock sample video writer: \(message)"
      case let .videoEncodingNotSupported(codec):
        return "Video encoding is not supported for codec: \(codec)."
      case let .failedToStartVideoWriter(message):
        return "Failed to start mock sample video writer: \(message)"
      case let .failedToCreatePixelBuffer(message):
        return "Failed to create pixel buffer for mock sample: \(message)"
      case let .failedToAppendVideoFrame(message):
        return "Failed to append frame to mock sample: \(message)"
      case let .failedToFinishVideoWriter(message):
        return "Failed to finish mock sample video: \(message)"
      case let .failedToGenerateVideo(message):
        return "Failed to generate mock sample video: \(message)"
      }
    }
  }

  private(set) var isEnabled: Bool = false

#if DEBUG
  private var activeDevice: (any MockRaybanMeta)?
#endif

  func enableMockDevice() async throws {
#if DEBUG
    let device = try pairOrReuseDevice()
    try await configureDefaultMockMedia(for: device)
    device.powerOn()
    device.unfold()
    device.don()

    activeDevice = device
    isEnabled = true
#else
    isEnabled = false
#endif
  }

  func disableMockDevice() {
#if DEBUG
    activeDevice?.doff()
    activeDevice?.fold()
    activeDevice?.powerOff()
    for device in MockDeviceKit.shared.pairedDevices {
      MockDeviceKit.shared.unpairDevice(device)
    }
    activeDevice = nil
#endif
    isEnabled = false
  }
}

#if DEBUG
private extension MockDeviceController {
  func pairOrReuseDevice() throws -> any MockRaybanMeta {
    let kit = MockDeviceKit.shared
    if let paired = kit.pairedDevices.first {
      guard let rayban = paired as? any MockRaybanMeta else {
        throw MockDeviceControllerError.pairedDeviceIsNotRaybanMeta
      }
      return rayban
    }

    return kit.pairRaybanMeta()
  }

  func configureDefaultMockMedia(for device: any MockRaybanMeta) async throws {
    let mediaDirectoryURL = try ensureMediaDirectory()
    let imageURL = mediaDirectoryURL.appendingPathComponent(MockMediaDefaults.imageFileName)
    let videoURL = mediaDirectoryURL.appendingPathComponent(MockMediaDefaults.videoFileName)

    try await Task.detached(priority: .utility) {
      try Self.generateDefaultImage(at: imageURL)
      try await Self.generateDefaultVideo(at: videoURL)
    }.value

    let cameraKit = device.getCameraKit()
    await cameraKit.setCameraFeed(fileURL: videoURL)
    await cameraKit.setCapturedImage(fileURL: imageURL)
  }

  func ensureMediaDirectory() throws -> URL {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(MockMediaDefaults.mediaDirectoryName, isDirectory: true)
    do {
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    } catch {
      throw MockDeviceControllerError.failedToCreateTempDirectory(error.localizedDescription)
    }
    return directory
  }

  nonisolated static func generateDefaultImage(at fileURL: URL) throws {
    let width = 320
    let height = 240
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    let bitmapInfo = CGImageAlphaInfo.premultipliedLast.rawValue
    guard
      let context = CGContext(
        data: nil,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: 0,
        space: colorSpace,
        bitmapInfo: bitmapInfo
      )
    else {
      throw MockDeviceControllerError.failedToGenerateDefaultImage("Unable to allocate bitmap context.")
    }

    let size = CGSize(width: width, height: height)
    context.setFillColor(red: 0.07, green: 0.22, blue: 0.45, alpha: 1.0)
    context.fill(CGRect(origin: .zero, size: size))
    context.setFillColor(red: 0.92, green: 0.95, blue: 0.98, alpha: 1.0)
    context.fill(CGRect(x: 24, y: 24, width: size.width - 48, height: size.height - 48))

    guard let image = context.makeImage() else {
      throw MockDeviceControllerError.failedToGenerateDefaultImage("Unable to create image from bitmap context.")
    }

    guard
      let destination = CGImageDestinationCreateWithURL(
        fileURL as CFURL,
        UTType.jpeg.identifier as CFString,
        1,
        nil
      )
    else {
      throw MockDeviceControllerError.failedToWriteDefaultImage("Unable to create JPEG destination.")
    }

    let options: [CFString: Any] = [
      kCGImageDestinationLossyCompressionQuality: 0.85
    ]
    CGImageDestinationAddImage(destination, image, options as CFDictionary)
    guard CGImageDestinationFinalize(destination) else {
      throw MockDeviceControllerError.failedToWriteDefaultImage("Failed to finalize JPEG image destination.")
    }
  }

  nonisolated static func generateDefaultVideo(at fileURL: URL) async throws {
    let candidateCodecs: [AVVideoCodecType] = [.hevc, .h264]
    var failures: [String] = []

    for codec in candidateCodecs {
      do {
        try await generateDefaultVideo(at: fileURL, codec: codec)
        return
      } catch {
        failures.append("\(codecLabel(codec)): \(error.localizedDescription)")
      }
    }

    throw MockDeviceControllerError.failedToGenerateVideo(failures.joined(separator: " | "))
  }

  nonisolated static func generateDefaultVideo(at fileURL: URL, codec: AVVideoCodecType) async throws {
    let width = 320
    let height = 240
    let frameCount = 24
    let frameRate: Int32 = 24

    if FileManager.default.fileExists(atPath: fileURL.path) {
      do {
        try FileManager.default.removeItem(at: fileURL)
      } catch {
        throw MockDeviceControllerError.failedToCreateVideoWriter("Could not remove existing video: \(error.localizedDescription)")
      }
    }

    let writer: AVAssetWriter
    do {
      writer = try AVAssetWriter(url: fileURL, fileType: .mov)
    } catch {
      throw MockDeviceControllerError.failedToCreateVideoWriter(error.localizedDescription)
    }

    let settings: [String: Any] = [
      AVVideoCodecKey: codec,
      AVVideoWidthKey: width,
      AVVideoHeightKey: height,
      AVVideoCompressionPropertiesKey: [
        AVVideoAverageBitRateKey: 300_000
      ]
    ]

    guard writer.canApply(outputSettings: settings, forMediaType: .video) else {
      throw MockDeviceControllerError.videoEncodingNotSupported(codecLabel(codec))
    }

    let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
    input.expectsMediaDataInRealTime = false
    guard writer.canAdd(input) else {
      throw MockDeviceControllerError.videoEncodingNotSupported(codecLabel(codec))
    }
    writer.add(input)

    let attributes: [String: Any] = [
      kCVPixelBufferPixelFormatTypeKey as String: Int(kCVPixelFormatType_32BGRA),
      kCVPixelBufferWidthKey as String: width,
      kCVPixelBufferHeightKey as String: height,
      kCVPixelBufferCGBitmapContextCompatibilityKey as String: true,
      kCVPixelBufferCGImageCompatibilityKey as String: true
    ]
    let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: attributes)

    guard writer.startWriting() else {
      throw MockDeviceControllerError.failedToStartVideoWriter(
        "\(codecLabel(codec)): \(writer.error?.localizedDescription ?? "Unknown writer start error.")"
      )
    }
    writer.startSession(atSourceTime: .zero)

    for index in 0..<frameCount {
      while input.isReadyForMoreMediaData == false {
        try await Task.sleep(nanoseconds: 5_000_000)
      }

      let pixelBuffer = try makePixelBuffer(frameIndex: index)
      let presentationTime = CMTime(value: CMTimeValue(index), timescale: frameRate)
      guard adaptor.append(pixelBuffer, withPresentationTime: presentationTime) else {
        throw MockDeviceControllerError.failedToAppendVideoFrame(
          "\(codecLabel(codec)): \(writer.error?.localizedDescription ?? "Pixel buffer append failed.")"
        )
      }
    }

    input.markAsFinished()
    try await finishWriting(writer)
  }

  nonisolated static func finishWriting(_ writer: AVAssetWriter) async throws {
    await writer.finishWriting()
    guard writer.status == .completed else {
      throw MockDeviceControllerError.failedToFinishVideoWriter(
        writer.error?.localizedDescription ?? "Writer status: \(writer.status.rawValue)"
      )
    }
  }

  nonisolated static func makePixelBuffer(frameIndex: Int) throws -> CVPixelBuffer {
    let width = 320
    let height = 240

    var pixelBuffer: CVPixelBuffer?
    let status = CVPixelBufferCreate(
      kCFAllocatorDefault,
      width,
      height,
      kCVPixelFormatType_32BGRA,
      nil,
      &pixelBuffer
    )
    guard status == kCVReturnSuccess, let pixelBuffer else {
      throw MockDeviceControllerError.failedToCreatePixelBuffer("CVPixelBufferCreate status \(status).")
    }

    CVPixelBufferLockBaseAddress(pixelBuffer, [])
    defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, []) }

    guard let baseAddress = CVPixelBufferGetBaseAddress(pixelBuffer) else {
      throw MockDeviceControllerError.failedToCreatePixelBuffer("Base address unavailable.")
    }

    let bytesPerRow = CVPixelBufferGetBytesPerRow(pixelBuffer)
    let pointer = baseAddress.assumingMemoryBound(to: UInt8.self)
    let horizonY = Int(Double(height) * 0.58)
    let drift = (frameIndex * 2) % max(1, width)
    let sunCenterX = Int(Double(width) * 0.78)
    let sunCenterY = Int(Double(height) * 0.22)
    let sunRadius = max(10, width / 10)

    for y in 0..<height {
      let row = pointer.advanced(by: y * bytesPerRow)
      for x in 0..<width {
        let offset = x * 4

        var red: Int
        var green: Int
        var blue: Int

        if y < horizonY {
          let skyMix = Double(y) / Double(max(1, horizonY))
          red = Int(80 + skyMix * 40)
          green = Int(140 + skyMix * 45)
          blue = Int(195 + skyMix * 35)
        } else {
          let groundMix = Double(y - horizonY) / Double(max(1, height - horizonY))
          red = Int(70 + groundMix * 25)
          green = Int(95 + groundMix * 30)
          blue = Int(85 + groundMix * 18)
        }

        // Add a simple moving bright stripe to show the feed is live.
        if abs((x + drift) % width - width / 2) < 10, y > horizonY {
          red += 24
          green += 24
          blue += 24
        }

        // Draw a soft "sun" highlight.
        let dx = x - sunCenterX
        let dy = y - sunCenterY
        if (dx * dx + dy * dy) < (sunRadius * sunRadius) {
          red += 55
          green += 45
          blue += 10
        }

        row[offset] = UInt8(clamping: blue)      // B
        row[offset + 1] = UInt8(clamping: green) // G
        row[offset + 2] = UInt8(clamping: red)   // R
        row[offset + 3] = 255                    // A
      }
    }

    return pixelBuffer
  }

  nonisolated static func codecLabel(_ codec: AVVideoCodecType) -> String {
    switch codec {
    case .hevc:
      return "HEVC"
    case .h264:
      return "H264"
    default:
      return codec.rawValue
    }
  }
}
#endif
