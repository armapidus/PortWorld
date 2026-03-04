import Foundation

/// Shared URLProtocol stub for HTTP request/response testing with URLSession.
enum TestHTTPStubResult {
  case success(statusCode: Int = 200, headers: [String: String] = [:], data: Data = Data())
  case failure(Error)
}

final class TestURLProtocolStub: URLProtocol {
  private static let lock = NSLock()
  private static var requests: [URLRequest] = []
  private static var handler: ((URLRequest) -> TestHTTPStubResult)?

  static func setHandler(_ newHandler: @escaping (URLRequest) -> TestHTTPStubResult) {
    lock.lock()
    handler = newHandler
    lock.unlock()
  }

  static func reset() {
    lock.lock()
    requests = []
    handler = nil
    lock.unlock()
  }

  static func requestCount() -> Int {
    lock.lock()
    defer { lock.unlock() }
    return requests.count
  }

  static func receivedRequests() -> [URLRequest] {
    lock.lock()
    defer { lock.unlock() }
    return requests
  }

  static func makeEphemeralSession() -> URLSession {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [Self.self]
    return URLSession(configuration: configuration)
  }

  override class func canInit(with request: URLRequest) -> Bool {
    true
  }

  override class func canonicalRequest(for request: URLRequest) -> URLRequest {
    request
  }

  override func startLoading() {
    Self.lock.lock()
    Self.requests.append(request)
    let activeHandler = Self.handler
    Self.lock.unlock()

    guard let activeHandler else {
      client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
      return
    }

    switch activeHandler(request) {
    case .success(let statusCode, let headers, let data):
      let response = HTTPURLResponse(
        url: request.url ?? URL(string: "https://example.invalid")!,
        statusCode: statusCode,
        httpVersion: "HTTP/1.1",
        headerFields: headers
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
