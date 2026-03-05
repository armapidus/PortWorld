import AVFoundation
import CoreMedia
import CoreVideo
import Foundation
import UIKit

#if DEBUG
import MWDATMockDevice
#endif

@MainActor
final class MockDeviceController {
  enum MockDeviceControllerError: LocalizedError {
    case failedToCreateTempDirectory(String)
    case failedToGenerateDefaultImage(String)
    case failedToWriteDefaultImage(String)
    case pairedDeviceIsNotRaybanMeta
    case failedToCreateVideoWriter(String)
    case hevcEncodingNotSupported
    case failedToStartVideoWriter(String)
    case failedToCreatePixelBuffer(String)
    case failedToAppendVideoFrame(String)
    case failedToFinishVideoWriter(String)

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
        return "Failed to create HEVC sample video writer: \(message)"
      case .hevcEncodingNotSupported:
        return "HEVC encoding is not supported on this runtime."
      case let .failedToStartVideoWriter(message):
        return "Failed to start HEVC sample video writer: \(message)"
      case let .failedToCreatePixelBuffer(message):
        return "Failed to create pixel buffer for HEVC sample: \(message)"
      case let .failedToAppendVideoFrame(message):
        return "Failed to append frame to HEVC sample: \(message)"
      case let .failedToFinishVideoWriter(message):
        return "Failed to finish HEVC sample video: \(message)"
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
  static let mediaDirectoryName = "portworld-mock-device"
  static let imageFileName = "default-captured-image.jpg"
  static let videoFileName = "default-camera-feed.mov"
  static let videoWidth = 320
  static let videoHeight = 240
  static let videoFPS: Int32 = 24
  static let videoFrameCount = 24

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
    let imageURL = mediaDirectoryURL.appendingPathComponent(Self.imageFileName)
    let videoURL = mediaDirectoryURL.appendingPathComponent(Self.videoFileName)

    try generateDefaultImage(at: imageURL)
    try await generateDefaultVideo(at: videoURL)

    let cameraKit = device.getCameraKit()
    await cameraKit.setCameraFeed(fileURL: videoURL)
    await cameraKit.setCapturedImage(fileURL: imageURL)
  }

  func ensureMediaDirectory() throws -> URL {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(Self.mediaDirectoryName, isDirectory: true)
    do {
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    } catch {
      throw MockDeviceControllerError.failedToCreateTempDirectory(error.localizedDescription)
    }
    return directory
  }

  func generateDefaultImage(at fileURL: URL) throws {
    let size = CGSize(width: Self.videoWidth, height: Self.videoHeight)
    let renderer = UIGraphicsImageRenderer(size: size)
    let image = renderer.image { context in
      UIColor(red: 0.07, green: 0.22, blue: 0.45, alpha: 1.0).setFill()
      context.fill(CGRect(origin: .zero, size: size))
      UIColor(red: 0.92, green: 0.95, blue: 0.98, alpha: 1.0).setFill()
      context.fill(CGRect(x: 24, y: 24, width: size.width - 48, height: size.height - 48))
    }

    guard let data = image.jpegData(compressionQuality: 0.85) else {
      throw MockDeviceControllerError.failedToGenerateDefaultImage("JPEG encoding returned nil.")
    }

    do {
      try data.write(to: fileURL, options: .atomic)
    } catch {
      throw MockDeviceControllerError.failedToWriteDefaultImage(error.localizedDescription)
    }
  }

  func generateDefaultVideo(at fileURL: URL) async throws {
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
      AVVideoCodecKey: AVVideoCodecType.hevc,
      AVVideoWidthKey: Self.videoWidth,
      AVVideoHeightKey: Self.videoHeight,
      AVVideoCompressionPropertiesKey: [
        AVVideoAverageBitRateKey: 300_000
      ]
    ]

    guard writer.canApply(outputSettings: settings, forMediaType: .video) else {
      throw MockDeviceControllerError.hevcEncodingNotSupported
    }

    let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
    input.expectsMediaDataInRealTime = false
    guard writer.canAdd(input) else {
      throw MockDeviceControllerError.hevcEncodingNotSupported
    }
    writer.add(input)

    let attributes: [String: Any] = [
      kCVPixelBufferPixelFormatTypeKey as String: Int(kCVPixelFormatType_32BGRA),
      kCVPixelBufferWidthKey as String: Self.videoWidth,
      kCVPixelBufferHeightKey as String: Self.videoHeight,
      kCVPixelBufferCGBitmapContextCompatibilityKey as String: true,
      kCVPixelBufferCGImageCompatibilityKey as String: true
    ]
    let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: attributes)

    guard writer.startWriting() else {
      throw MockDeviceControllerError.failedToStartVideoWriter(writer.error?.localizedDescription ?? "Unknown writer start error.")
    }
    writer.startSession(atSourceTime: .zero)

    for index in 0..<Self.videoFrameCount {
      while input.isReadyForMoreMediaData == false {
        try await Task.sleep(nanoseconds: 5_000_000)
      }

      let pixelBuffer = try makePixelBuffer(frameIndex: index)
      let presentationTime = CMTime(value: CMTimeValue(index), timescale: Self.videoFPS)
      guard adaptor.append(pixelBuffer, withPresentationTime: presentationTime) else {
        throw MockDeviceControllerError.failedToAppendVideoFrame(writer.error?.localizedDescription ?? "Pixel buffer append failed.")
      }
    }

    input.markAsFinished()
    try await finishWriting(writer)
  }

  func finishWriting(_ writer: AVAssetWriter) async throws {
    try await withCheckedThrowingContinuation { continuation in
      writer.finishWriting {
        if writer.status == .completed {
          continuation.resume()
          return
        }

        continuation.resume(
          throwing: MockDeviceControllerError.failedToFinishVideoWriter(
            writer.error?.localizedDescription ?? "Writer status: \(writer.status.rawValue)"
          )
        )
      }
    }
  }

  func makePixelBuffer(frameIndex: Int) throws -> CVPixelBuffer {
    var pixelBuffer: CVPixelBuffer?
    let status = CVPixelBufferCreate(
      kCFAllocatorDefault,
      Self.videoWidth,
      Self.videoHeight,
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
    let t = UInt8((frameIndex * 8) % 255)

    for y in 0..<Self.videoHeight {
      let row = pointer.advanced(by: y * bytesPerRow)
      for x in 0..<Self.videoWidth {
        let offset = x * 4
        row[offset] = UInt8((x + Int(t)) % 255)
        row[offset + 1] = UInt8((y + Int(t)) % 255)
        row[offset + 2] = UInt8((Int(t) + 48) % 255)
        row[offset + 3] = 255
      }
    }

    return pixelBuffer
  }
}
#endif
