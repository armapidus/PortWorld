import Foundation

struct RuntimeConfig {
  let backendBaseURL: URL
  let webSocketURL: URL
  let apiKey: String
  let bearerToken: String
  let wakePhrase: String
  let sleepPhrase: String
  let wakeWordMode: WakeWordMode
  let wakeWordLocaleIdentifier: String
  let wakeWordRequiresOnDeviceRecognition: Bool
  let wakeWordDetectionCooldownMs: Int64
  let assistantStuckDetectionThresholdMs: Int64

  var requestHeaders: [String: String] {
    var headers: [String: String] = [:]
    let trimmedAPIKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
    if !trimmedAPIKey.isEmpty {
      headers["X-API-Key"] = trimmedAPIKey
    }

    let trimmedBearerToken = bearerToken.trimmingCharacters(in: .whitespacesAndNewlines)
    if !trimmedBearerToken.isEmpty {
      headers["Authorization"] = "Bearer \(trimmedBearerToken)"
    }

    return headers
  }

  var backendSummary: String {
    "base=\(backendBaseURL.absoluteString) ws=\(webSocketURL.absoluteString)"
  }

  static func load(from bundle: Bundle = .main) -> RuntimeConfig {
    let backendBaseURL = resolveURL(
      infoPlistKey: "SON_BACKEND_BASE_URL",
      defaultURLString: "http://127.0.0.1:8080",
      bundle: bundle
    )
    let wsPath = resolvePath(
      infoPlistKey: "SON_WS_PATH",
      defaultPath: "/ws/session",
      bundle: bundle
    )
    let explicitWSURL = resolveOptionalURL(infoPlistKey: "SON_WS_URL", bundle: bundle)

    return RuntimeConfig(
      backendBaseURL: backendBaseURL,
      webSocketURL: explicitWSURL ?? deriveWebSocketURL(baseURL: backendBaseURL, path: wsPath),
      apiKey: resolveString(infoPlistKey: "SON_API_KEY", defaultValue: "", bundle: bundle),
      bearerToken: resolveString(infoPlistKey: "SON_BEARER_TOKEN", defaultValue: "", bundle: bundle),
      wakePhrase: resolveString(infoPlistKey: "SON_WAKE_PHRASE", defaultValue: "hey mario", bundle: bundle),
      sleepPhrase: resolveString(infoPlistKey: "SON_SLEEP_PHRASE", defaultValue: "goodbye mario", bundle: bundle),
      wakeWordMode: resolveWakeWordMode(bundle: bundle),
      wakeWordLocaleIdentifier: resolveString(infoPlistKey: "SON_WAKE_LOCALE", defaultValue: "en-US", bundle: bundle),
      wakeWordRequiresOnDeviceRecognition: resolveBool(
        infoPlistKey: "SON_WAKE_REQUIRE_ON_DEVICE",
        defaultValue: true,
        bundle: bundle
      ),
      wakeWordDetectionCooldownMs: resolveInt64(
        infoPlistKey: "SON_WAKE_DETECTION_COOLDOWN_MS",
        defaultValue: 1_500,
        minimum: 0,
        bundle: bundle
      ),
      assistantStuckDetectionThresholdMs: resolveInt64(
        infoPlistKey: "SON_ASSISTANT_STUCK_DETECTION_THRESHOLD_MS",
        defaultValue: 1_500,
        minimum: 250,
        bundle: bundle
      )
    )
  }

  private static func resolveWakeWordMode(bundle: Bundle) -> WakeWordMode {
    let rawValue = resolveString(
      infoPlistKey: "SON_WAKE_MODE",
      defaultValue: WakeWordMode.onDevicePreferred.rawValue,
      bundle: bundle
    )
    return WakeWordMode(rawValue: rawValue) ?? .onDevicePreferred
  }

  private static func resolveURL(infoPlistKey: String, defaultURLString: String, bundle: Bundle) -> URL {
    let rawValue = resolveString(infoPlistKey: infoPlistKey, defaultValue: defaultURLString, bundle: bundle)
    return URL(string: rawValue) ?? URL(string: defaultURLString)!
  }

  private static func resolveOptionalURL(infoPlistKey: String, bundle: Bundle) -> URL? {
    let rawValue = resolveString(infoPlistKey: infoPlistKey, defaultValue: "", bundle: bundle)
    guard !rawValue.isEmpty else { return nil }
    return URL(string: rawValue)
  }

  private static func resolvePath(infoPlistKey: String, defaultPath: String, bundle: Bundle) -> String {
    let rawValue = resolveString(infoPlistKey: infoPlistKey, defaultValue: defaultPath, bundle: bundle)
    return rawValue.hasPrefix("/") ? rawValue : "/" + rawValue
  }

  private static func deriveWebSocketURL(baseURL: URL, path: String) -> URL {
    var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
    components?.scheme = baseURL.scheme == "https" ? "wss" : "ws"
    components?.path = path
    return components?.url ?? baseURL
  }

  private static func resolveString(infoPlistKey: String, defaultValue: String, bundle: Bundle) -> String {
    guard let rawValue = bundle.object(forInfoDictionaryKey: infoPlistKey) as? String else {
      return defaultValue
    }

    let trimmedValue = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmedValue.isEmpty ? defaultValue : trimmedValue
  }

  private static func resolveBool(infoPlistKey: String, defaultValue: Bool, bundle: Bundle) -> Bool {
    if let rawValue = bundle.object(forInfoDictionaryKey: infoPlistKey) as? NSNumber {
      return rawValue.boolValue
    }

    if let rawValue = bundle.object(forInfoDictionaryKey: infoPlistKey) as? String {
      switch rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
      case "1", "true", "yes", "on":
        return true
      case "0", "false", "no", "off":
        return false
      default:
        break
      }
    }

    return defaultValue
  }

  private static func resolveInt64(
    infoPlistKey: String,
    defaultValue: Int64,
    minimum: Int64,
    bundle: Bundle
  ) -> Int64 {
    if let rawValue = bundle.object(forInfoDictionaryKey: infoPlistKey) as? NSNumber {
      return max(minimum, rawValue.int64Value)
    }

    if let rawValue = bundle.object(forInfoDictionaryKey: infoPlistKey) as? String,
       let parsedValue = Int64(rawValue.trimmingCharacters(in: .whitespacesAndNewlines))
    {
      return max(minimum, parsedValue)
    }

    return max(minimum, defaultValue)
  }
}
