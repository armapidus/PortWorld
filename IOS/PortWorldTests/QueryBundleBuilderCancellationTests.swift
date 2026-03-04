import Foundation
import XCTest
@testable import PortWorld

final class QueryBundleBuilderCancellationTests: XCTestCase {

  override func setUp() {
    super.setUp()
    StubUploadURLProtocol.reset()
  }

  override func tearDown() {
    StubUploadURLProtocol.reset()
    super.tearDown()
  }

  func testUploadPreservesCancellationErrorWithoutRetry() async throws {
    StubUploadURLProtocol.responseHandler = { _ in
      .failure(CancellationError())
    }

    let builder = makeBuilder(maxRetryCount: 2)

    do {
      _ = try await builder.uploadQueryBundle(
        metadata: Self.makeMetadata(),
        audioFileURL: Self.makeTempFile(named: "audio.wav", bytes: [0x00, 0x01]),
        videoFileURL: Self.makeTempFile(named: "video.mp4", bytes: [0x10, 0x11])
      )
      XCTFail("Expected cancellation")
    } catch {
      XCTAssertTrue(error is CancellationError)
      XCTAssertFalse(error is QueryBundleBuilderError)
      XCTAssertEqual(StubUploadURLProtocol.requestCount(), 1)
    }
  }

  func testUploadMapsURLErrorCancelledToCancellationWithoutRetry() async throws {
    StubUploadURLProtocol.responseHandler = { _ in
      .failure(URLError(.cancelled))
    }

    let builder = makeBuilder(maxRetryCount: 2)

    do {
      _ = try await builder.uploadQueryBundle(
        metadata: Self.makeMetadata(),
        audioFileURL: Self.makeTempFile(named: "audio.wav", bytes: [0x02, 0x03]),
        videoFileURL: Self.makeTempFile(named: "video.mp4", bytes: [0x12, 0x13])
      )
      XCTFail("Expected cancellation")
    } catch {
      XCTAssertTrue(error is CancellationError)
      XCTAssertFalse(error is QueryBundleBuilderError)
      XCTAssertEqual(StubUploadURLProtocol.requestCount(), 1)
    }
  }

  private func makeBuilder(maxRetryCount: Int) -> QueryBundleBuilder {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [StubUploadURLProtocol.self]
    let urlSession = URLSession(configuration: configuration)

    return QueryBundleBuilder(
      endpointURL: URL(string: "https://example.invalid/query")!,
      maxRetryCount: maxRetryCount,
      baseRetryDelayMs: 1,
      maxRetryDelayMs: 1,
      urlSession: urlSession
    )
  }

  private static func makeMetadata() -> QueryMetadata {
    QueryMetadata(
      sessionID: "sess_1",
      queryID: "query_1",
      wakeTsMs: 1,
      queryStartTsMs: 2,
      queryEndTsMs: 3,
      videoStartTsMs: 2,
      videoEndTsMs: 3
    )
  }

  private static func makeTempFile(named fileName: String, bytes: [UInt8]) -> URL {
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("\(UUID().uuidString)-\(fileName)")

    try? FileManager.default.removeItem(at: url)
    do {
      try Data(bytes).write(to: url)
    } catch {
      XCTFail("Failed to write temp file at \(url.path): \(error.localizedDescription)")
    }

    return url
  }
}

private final class StubUploadURLProtocol: URLProtocol {
  enum StubResult {
    case success(statusCode: Int, data: Data)
    case failure(Error)
  }

  private static let lock = NSLock()
  private static var requests: Int = 0
  static var responseHandler: ((URLRequest) -> StubResult)?

  static func reset() {
    lock.lock()
    requests = 0
    responseHandler = nil
    lock.unlock()
  }

  static func requestCount() -> Int {
    lock.lock()
    defer { lock.unlock() }
    return requests
  }

  override class func canInit(with request: URLRequest) -> Bool {
    true
  }

  override class func canonicalRequest(for request: URLRequest) -> URLRequest {
    request
  }

  override func startLoading() {
    Self.lock.lock()
    Self.requests += 1
    let handler = Self.responseHandler
    Self.lock.unlock()

    guard let handler else {
      client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
      return
    }

    switch handler(request) {
    case .success(let statusCode, let data):
      let response = HTTPURLResponse(
        url: request.url ?? URL(string: "https://example.invalid")!,
        statusCode: statusCode,
        httpVersion: "HTTP/1.1",
        headerFields: ["Content-Type": "application/json"]
      )!
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      if !data.isEmpty {
        client?.urlProtocol(self, didLoad: data)
      }
      client?.urlProtocolDidFinishLoading(self)
    case .failure(let error):
      client?.urlProtocol(self, didFailWithError: error)
    }
  }

  override func stopLoading() {}
}
