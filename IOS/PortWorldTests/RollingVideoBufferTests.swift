import AVFoundation
import UIKit
import XCTest
@testable import PortWorld

final class RollingVideoBufferTests: XCTestCase {

  func testRetentionWindowEvictsExpiredFrames() async throws {
    let buffer = RollingVideoBuffer(maxDurationMs: 5_000)

    for i in 0..<10 {
      let color: UIColor = i.isMultiple(of: 2) ? .red : .blue
      await buffer.append(frame: Self.makeImage(color), timestampMs: Int64(i * 1_000))
    }

    let frameCount = await buffer.bufferedFrameCount
    let bufferedDurationMs = await buffer.bufferedDurationMs
    XCTAssertEqual(frameCount, 6)
    XCTAssertEqual(bufferedDurationMs, 5_000)

    do {
      _ = try await buffer.exportInterval(startTimestampMs: 0, endTimestampMs: 3_999)
      XCTFail("Expected no frames in evicted interval")
    } catch let error as RollingVideoBufferError {
      guard case .noFramesInInterval(let startMs, let endMs) = error else {
        XCTFail("Unexpected error: \(error)")
        return
      }
      XCTAssertEqual(startMs, 0)
      XCTAssertEqual(endMs, 3_999)
    }

    let recentExport = try await buffer.exportInterval(startTimestampMs: 4_000, endTimestampMs: 9_000)
    XCTAssertGreaterThan(recentExport.frameCount, 0)
    XCTAssertGreaterThan(recentExport.bytesWritten, 0)

    await buffer.clear()
  }

  func testExportProducesValidPlayableMP4() async throws {
    let buffer = RollingVideoBuffer(maxDurationMs: 5_000)
    let outputURL = Self.makeTempOutputURL(fileName: "export-validity.mp4")
    Self.removeFileIfPresent(outputURL)

    await buffer.append(frame: Self.makeImage(.red), timestampMs: 1_000)
    await buffer.append(frame: Self.makeImage(.green), timestampMs: 1_100)
    await buffer.append(frame: Self.makeImage(.blue), timestampMs: 1_200)

    let result = try await buffer.exportInterval(
      startTimestampMs: 1_000,
      endTimestampMs: 1_300,
      outputURL: outputURL,
      bitrate: 2_000_000
    )

    XCTAssertEqual(result.outputURL, outputURL)
    XCTAssertEqual(result.durationMs, 300)
    XCTAssertGreaterThanOrEqual(result.frameCount, 3)
    XCTAssertGreaterThan(result.bytesWritten, 0)
    XCTAssertTrue(FileManager.default.fileExists(atPath: outputURL.path))

    let asset = AVURLAsset(url: outputURL)
    let isPlayable = try await asset.load(.isPlayable)
    let duration = try await asset.load(.duration)
    let videoTracks = try await asset.loadTracks(withMediaType: .video)

    XCTAssertTrue(isPlayable)
    XCTAssertFalse(videoTracks.isEmpty)
    XCTAssertGreaterThan(CMTimeGetSeconds(duration), 0)

    Self.removeFileIfPresent(outputURL)
  }

  func testExportCancellationRemovesPartialOutput() async throws {
    let signal = ExportHookSignal()

    let buffer = RollingVideoBuffer(
      maxDurationMs: 5_000,
      beforeAppendFrameHook: { _ in
        await signal.markStarted()
        try await Task.sleep(nanoseconds: 5_000_000_000)
      }
    )

    await buffer.append(frame: Self.makeImage(.red), timestampMs: 1_000)
    await buffer.append(frame: Self.makeImage(.green), timestampMs: 1_100)
    await buffer.append(frame: Self.makeImage(.blue), timestampMs: 1_200)

    let outputURL = Self.makeTempOutputURL(fileName: "cancel-cleanup.mp4")
    Self.removeFileIfPresent(outputURL)

    let exportTask = Task {
      try await buffer.exportInterval(
        startTimestampMs: 1_000,
        endTimestampMs: 1_300,
        outputURL: outputURL,
        bitrate: 2_000_000
      )
    }

    try await AsyncTestWait.until(timeout: 1.0) {
      await signal.hasStarted()
    }
    exportTask.cancel()

    do {
      _ = try await exportTask.value
      XCTFail("Expected cancellation")
    } catch {
      XCTAssertTrue(error is CancellationError)
    }

    XCTAssertFalse(FileManager.default.fileExists(atPath: outputURL.path))
  }

  private static func makeImage(_ color: UIColor, size: CGSize = CGSize(width: 32, height: 32)) -> UIImage {
    let renderer = UIGraphicsImageRenderer(size: size)
    return renderer.image { context in
      color.setFill()
      context.fill(CGRect(origin: .zero, size: size))
    }
  }

  private static func makeTempOutputURL(fileName: String) -> URL {
    FileManager.default.temporaryDirectory
      .appendingPathComponent("\(UUID().uuidString)-\(fileName)")
  }

  private static func removeFileIfPresent(_ url: URL) {
    try? FileManager.default.removeItem(at: url)
  }
}

private actor ExportHookSignal {
  private var started = false

  func markStarted() {
    started = true
  }

  func hasStarted() -> Bool {
    started
  }
}
