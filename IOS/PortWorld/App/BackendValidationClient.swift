import Foundation

struct BackendValidationClient {
  enum ValidationError: LocalizedError {
    case invalidBaseURL
    case unreachable
    case unexpectedResponse
    case healthCheckFailed(statusCode: Int)
    case readinessFailed(statusCode: Int)

    var errorDescription: String? {
      switch self {
      case .invalidBaseURL:
        return "Enter a valid backend URL."
      case .unreachable:
        return "The backend could not be reached."
      case .unexpectedResponse:
        return "The backend returned an unexpected response."
      case .healthCheckFailed(let statusCode):
        return "Health check failed with status \(statusCode)."
      case .readinessFailed(let statusCode):
        return "Readiness check failed with status \(statusCode)."
      }
    }
  }

  private let urlSession: URLSession

  init(urlSession: URLSession = .shared) {
    self.urlSession = urlSession
  }

  func validate(baseURLString: String, bearerToken: String) async throws {
    let trimmedBaseURL = baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)
    guard let baseURL = URL(string: trimmedBaseURL),
      let scheme = baseURL.scheme,
      scheme == "http" || scheme == "https"
    else {
      throw ValidationError.invalidBaseURL
    }

    try await performRequest(path: "/healthz", baseURL: baseURL, bearerToken: nil, endpoint: .health)

    let trimmedToken = bearerToken.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmedToken.isEmpty == false {
      try await performRequest(path: "/readyz", baseURL: baseURL, bearerToken: trimmedToken, endpoint: .ready)
    }
  }

  private func performRequest(
    path: String,
    baseURL: URL,
    bearerToken: String?,
    endpoint: ValidationEndpoint
  ) async throws {
    var request = URLRequest(url: appendPath(path, to: baseURL))
    request.httpMethod = "GET"
    request.timeoutInterval = 10

    if let bearerToken, bearerToken.isEmpty == false {
      request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
    }

    let response: URLResponse
    do {
      (_, response) = try await urlSession.data(for: request)
    } catch {
      throw ValidationError.unreachable
    }

    guard let httpResponse = response as? HTTPURLResponse else {
      throw ValidationError.unexpectedResponse
    }

    guard (200...299).contains(httpResponse.statusCode) else {
      switch endpoint {
      case .health:
        throw ValidationError.healthCheckFailed(statusCode: httpResponse.statusCode)
      case .ready:
        throw ValidationError.readinessFailed(statusCode: httpResponse.statusCode)
      }
    }
  }

  private func appendPath(_ path: String, to baseURL: URL) -> URL {
    guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
      return URL(string: baseURL.absoluteString + path) ?? baseURL
    }

    let basePath = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    let cleanPath = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))

    if basePath.isEmpty {
      components.path = "/\(cleanPath)"
    } else {
      components.path = "/\(basePath)/\(cleanPath)"
    }

    return components.url ?? baseURL
  }
}

private extension BackendValidationClient {
  enum ValidationEndpoint {
    case health
    case ready
  }
}
