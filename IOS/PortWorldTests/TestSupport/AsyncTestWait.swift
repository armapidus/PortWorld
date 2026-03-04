import Foundation
import XCTest

struct AsyncTestWaitTimeoutError: Error {}

enum AsyncTestWait {
  static func until(
    timeout: TimeInterval = 1.5,
    pollIntervalNs: UInt64 = 20_000_000,
    condition: @escaping () async -> Bool,
    file: StaticString = #filePath,
    line: UInt = #line
  ) async throws {
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
      if await condition() {
        return
      }
      try await Task.sleep(nanoseconds: pollIntervalNs)
    }

    XCTFail("Condition not met within \(timeout)s", file: file, line: line)
    throw AsyncTestWaitTimeoutError()
  }

  static func value<T>(
    timeout: TimeInterval = 1.5,
    pollIntervalNs: UInt64 = 20_000_000,
    resolver: @escaping () async -> T?,
    file: StaticString = #filePath,
    line: UInt = #line
  ) async throws -> T {
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
      if let resolved = await resolver() {
        return resolved
      }
      try await Task.sleep(nanoseconds: pollIntervalNs)
    }

    XCTFail("Value not available within \(timeout)s", file: file, line: line)
    throw AsyncTestWaitTimeoutError()
  }
}
