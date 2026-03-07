import Foundation
import Network
import UIKit

// Legacy photo-uploader contract retained only for the archived assistant runtime.
typealias VisionFrameSessionIDProvider = () -> String?
typealias VisionFrameUploadResultHandler = (VisionFrameUploadResult) -> Void

protocol VisionFrameUploaderProtocol: Actor {
  func bindHandlers(
    sessionIDProvider: @escaping VisionFrameSessionIDProvider,
    onUploadResult: VisionFrameUploadResultHandler?
  )
  func start()
  func stop()
  func consumeFrameDropCount() -> Int
  func submitLatestFrame(_ image: UIImage, captureTimestampMs: Int64)
}

struct VisionFrameUploadResult: Sendable {
  let frameId: String
  let captureTimestampMs: Int64
  let latencyMs: Int64
  let payloadBytes: Int
  let frameDropCount: Int
  let httpStatusCode: Int?
  let attemptCount: Int
  let success: Bool
  let errorCode: String?
  let errorDescription: String?
}

enum VisionFrameUploaderError: LocalizedError {
  case noSessionID
  case imageEncodingFailed

  var errorDescription: String? {
    switch self {
    case .noSessionID:
      return "Cannot upload vision frame without a session ID"
    case .imageEncodingFailed:
      return "Unable to JPEG-encode frame"
    }
  }
}

enum VisionFrameUploadErrorCode: String {
  case noSessionID = "PHOTO_UPLOAD_NO_SESSION_ID"
  case imageEncodingFailed = "PHOTO_UPLOAD_IMAGE_ENCODING_FAILED"
  case localNetworkDenied = "PHOTO_UPLOAD_LOCAL_NETWORK_DENIED"
  case timeout = "PHOTO_UPLOAD_TIMEOUT"
  case network = "PHOTO_UPLOAD_NETWORK_ERROR"
  case server = "PHOTO_UPLOAD_HTTP_ERROR"
  case unknown = "PHOTO_UPLOAD_UNKNOWN_ERROR"
}

actor VisionFrameUploader: VisionFrameUploaderProtocol {
  typealias UploadResultHandler = (VisionFrameUploadResult) -> Void
  private static let networkPathKey = "_NSURLErrorNWPathKey"

  private var onUploadResult: UploadResultHandler?

  private struct PendingFrame {
    let image: UIImage
    let captureTimestampMs: Int64
  }

  private let endpointURL: URL
  private let defaultHeaders: [String: String]
  private var sessionIDProvider: () -> String?
  private let uploadIntervalMs: Int64
  private let jpegCompression: CGFloat
  private let requestTimeoutMs: Int64
  private let maxRetryCount: Int
  private let baseRetryDelayMs: Int64
  private let maxRetryDelayMs: Int64
  private let urlSession: URLSession

  private var loopTask: Task<Void, Never>?
  private var latestFrame: PendingFrame?
  private var isRunning = false
  private var uploadInFlight = false
  private var frameDropCount = 0
  private var frameDropCountSinceLastRead = 0

  init(
    endpointURL: URL,
    defaultHeaders: [String: String] = [:],
    sessionIDProvider: @escaping () -> String?,
    uploadIntervalMs: Int64 = 1_000,
    jpegCompression: CGFloat = 0.6,
    requestTimeoutMs: Int64 = 3_000,
    maxRetryCount: Int = 2,
    baseRetryDelayMs: Int64 = 250,
    maxRetryDelayMs: Int64 = 2_000,
    urlSession: URLSession = .shared
  ) {
    self.endpointURL = endpointURL
    self.defaultHeaders = defaultHeaders
    self.sessionIDProvider = sessionIDProvider
    self.uploadIntervalMs = max(100, uploadIntervalMs)
    self.jpegCompression = min(max(jpegCompression, 0.1), 1.0)
    self.requestTimeoutMs = max(500, requestTimeoutMs)
    self.maxRetryCount = max(0, maxRetryCount)
    self.baseRetryDelayMs = max(100, baseRetryDelayMs)
    self.maxRetryDelayMs = max(self.baseRetryDelayMs, maxRetryDelayMs)
    self.urlSession = urlSession
  }

  deinit {
    loopTask?.cancel()
  }

  func start() {
    guard !isRunning else {
      return
    }
    isRunning = true
    if loopTask == nil {
      loopTask = Task { [weak self] in
        await self?.runLoop()
      }
    }
  }

  func stop() {
    isRunning = false
    loopTask?.cancel()
    loopTask = nil
    latestFrame = nil
    frameDropCount = 0
    frameDropCountSinceLastRead = 0
  }

  /// Returns frame drops since last call, then resets the delta.
  func consumeFrameDropCount() -> Int {
    let count = frameDropCountSinceLastRead
    frameDropCountSinceLastRead = 0
    return count
  }

  func submitLatestFrame(_ image: UIImage, captureTimestampMs: Int64) {
    if latestFrame != nil {
      frameDropCount += 1
      frameDropCountSinceLastRead += 1
    } else if uploadInFlight {
      frameDropCount += 1
      frameDropCountSinceLastRead += 1
    }
    latestFrame = PendingFrame(image: image, captureTimestampMs: captureTimestampMs)
  }

  func bindHandlers(
    sessionIDProvider: @escaping VisionFrameSessionIDProvider,
    onUploadResult: UploadResultHandler?
  ) {
    self.sessionIDProvider = sessionIDProvider
    self.onUploadResult = onUploadResult
  }

  private func runLoop() async {
    while !Task.isCancelled {
      await tick()

      do {
        try await Task.sleep(nanoseconds: UInt64(uploadIntervalMs) * 1_000_000)
      } catch {
        break
      }
    }

    loopTask = nil
  }

  private func tick() async {
    guard isRunning else {
      return
    }

    guard !uploadInFlight else {
      return
    }

    guard let pending = latestFrame else {
      return
    }

    latestFrame = nil
    uploadInFlight = true

    do {
      let requestPayload = try await makeRequestPayload(pending)
      await upload(payload: requestPayload, captureTimestampMs: pending.captureTimestampMs, attempt: 1)
    } catch {
      uploadInFlight = false
      let frameId = "frame_\(pending.captureTimestampMs)"
      let errorCode: VisionFrameUploadErrorCode = (error as? VisionFrameUploaderError) == .noSessionID
        ? .noSessionID
        : .imageEncodingFailed
      publishResult(
        VisionFrameUploadResult(
          frameId: frameId,
          captureTimestampMs: pending.captureTimestampMs,
          latencyMs: 0,
          payloadBytes: 0,
          frameDropCount: self.frameDropCount,
          httpStatusCode: nil,
          attemptCount: 1,
          success: false,
          errorCode: errorCode.rawValue,
          errorDescription: error.localizedDescription
        )
      )
    }
  }

  private func makeRequestPayload(_ pending: PendingFrame) async throws -> (frameId: String, data: Data) {
    guard let sessionID = sessionIDProvider(), !sessionID.isEmpty else {
      throw VisionFrameUploaderError.noSessionID
    }

    let jpegData: Data
    if let encoded = await MainActor.run(body: { pending.image.jpegData(compressionQuality: jpegCompression) }) {
      jpegData = encoded
    } else {
      throw VisionFrameUploaderError.imageEncodingFailed
    }

    let now = Clocks.nowMs()
    let frameId = "frame_\(now)"
    let payloadData = try await MainActor.run { () throws -> Data in
      let dimensions = pending.image.normalizedPixelSize
      let body = VisionFrameRequest(
        sessionID: sessionID,
        tsMs: now,
        frameID: frameId,
        captureTsMs: pending.captureTimestampMs,
        width: dimensions.width,
        height: dimensions.height,
        frameB64: jpegData.base64EncodedString()
      )
      return try JSONEncoder().encode(body)
    }

    return (frameId, payloadData)
  }

  private func upload(payload: (frameId: String, data: Data), captureTimestampMs: Int64, attempt: Int) async {
    var request = URLRequest(url: endpointURL)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    for (name, value) in defaultHeaders {
      request.setValue(value, forHTTPHeaderField: name)
    }
    request.httpBody = payload.data
    request.timeoutInterval = TimeInterval(requestTimeoutMs) / 1000.0

    let startedAt = Date()

    let response: URLResponse?
    let error: Error?
    do {
      let (_, urlResponse) = try await urlSession.data(for: request)
      response = urlResponse
      error = nil
    } catch let requestError {
      response = nil
      error = requestError
    }

    let latencyMs = Int64(Date().timeIntervalSince(startedAt) * 1000)
    let statusCode = (response as? HTTPURLResponse)?.statusCode
    let success = error == nil && (statusCode.map { 200..<300 ~= $0 } ?? false)
    let errorCode = classifyError(error: error, statusCode: statusCode)
    let shouldRetry = shouldRetry(error: error, statusCode: statusCode, attempt: attempt)

    if success {
      uploadInFlight = false
      publishResult(
        VisionFrameUploadResult(
          frameId: payload.frameId,
          captureTimestampMs: captureTimestampMs,
          latencyMs: latencyMs,
          payloadBytes: payload.data.count,
          frameDropCount: self.frameDropCount,
          httpStatusCode: statusCode,
          attemptCount: attempt,
          success: true,
          errorCode: nil,
          errorDescription: nil
        )
      )
      return
    }

    if shouldRetry {
      let delayMs = retryDelayMs(forAttempt: attempt)

      do {
        try await Task.sleep(nanoseconds: UInt64(delayMs) * 1_000_000)
      } catch {
        uploadInFlight = false
        return
      }

      guard isRunning else {
        uploadInFlight = false
        return
      }

      await upload(payload: payload, captureTimestampMs: captureTimestampMs, attempt: attempt + 1)
      return
    }

    uploadInFlight = false
    publishResult(
      VisionFrameUploadResult(
        frameId: payload.frameId,
        captureTimestampMs: captureTimestampMs,
        latencyMs: latencyMs,
        payloadBytes: payload.data.count,
        frameDropCount: self.frameDropCount,
        httpStatusCode: statusCode,
        attemptCount: attempt,
        success: false,
        errorCode: errorCode.rawValue,
        errorDescription: uploadErrorDescription(errorCode: errorCode, error: error, statusCode: statusCode)
      )
    )
  }

  private func shouldRetry(error: Error?, statusCode: Int?, attempt: Int) -> Bool {
    guard attempt <= maxRetryCount else { return false }

    if let urlError = error as? URLError {
      if isLocalNetworkDenied(urlError) {
        return false
      }

      switch urlError.code {
      case .timedOut, .cannotConnectToHost, .networkConnectionLost, .notConnectedToInternet:
        return true
      default:
        return false
      }
    }

    guard let statusCode else { return false }
    return statusCode == 429 || (500...599).contains(statusCode)
  }

  private func classifyError(error: Error?, statusCode: Int?) -> VisionFrameUploadErrorCode {
    if let urlError = error as? URLError {
      if isLocalNetworkDenied(urlError) {
        return .localNetworkDenied
      }
      if urlError.code == .timedOut {
        return .timeout
      }
      return .network
    }

    if let statusCode, !(200..<300).contains(statusCode) {
      return .server
    }

    return .unknown
  }

  private func uploadErrorDescription(
    errorCode: VisionFrameUploadErrorCode,
    error: Error?,
    statusCode: Int?
  ) -> String {
    switch errorCode {
    case .localNetworkDenied:
      return "Local network access denied. Enable Local Network for PortWorld in iOS Settings > Privacy & Security > Local Network."
    case .server:
      return "HTTP \(statusCode ?? -1)"
    default:
      return error?.localizedDescription ?? "HTTP \(statusCode ?? -1)"
    }
  }

  private func isLocalNetworkDenied(_ urlError: URLError) -> Bool {
    if pathUnsatisfiedReason(from: urlError as NSError) == .localNetworkDenied {
      return true
    }

    if let underlyingError = (urlError as NSError).userInfo[NSUnderlyingErrorKey] as? NSError {
      return pathUnsatisfiedReason(from: underlyingError) == .localNetworkDenied
    }

    return false
  }

  private func pathUnsatisfiedReason(from error: NSError) -> NWPath.UnsatisfiedReason? {
    guard let path = error.userInfo[Self.networkPathKey] as? NWPath else {
      return nil
    }
    if #available(iOS 14.2, *) {
      return path.unsatisfiedReason
    }
    return nil
  }

  private func retryDelayMs(forAttempt attempt: Int) -> Int64 {
    let bounded = min(max(attempt - 1, 0), 6)
    let multiplier = Int64(1 << bounded)
    let scaled = min(baseRetryDelayMs * multiplier, maxRetryDelayMs)
    let jitter = Double.random(in: 0.85...1.15)
    return Int64(Double(scaled) * jitter)
  }

  private func publishResult(_ result: VisionFrameUploadResult) {
    let handler = onUploadResult
    Task { @MainActor in
      handler?(result)
    }
  }
}

private extension UIImage {
  nonisolated var normalizedPixelSize: (width: Int, height: Int) {
    if let cgImage {
      return (cgImage.width, cgImage.height)
    }

    let width = Int(size.width * scale)
    let height = Int(size.height * scale)
    return (max(1, width), max(1, height))
  }
}
