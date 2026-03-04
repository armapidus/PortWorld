import Foundation

/// Deterministic clock for tests that need explicit time progression.
/// @unchecked Sendable is safe here because all mutable state is guarded by `lock`.
final class DeterministicTestClock: @unchecked Sendable {
  private let lock = NSLock()
  private var nowMs: Int64

  init(initialNowMs: Int64 = 0) {
    self.nowMs = initialNowMs
  }

  func now() -> Int64 {
    lock.lock()
    defer { lock.unlock() }
    return nowMs
  }

  func set(_ value: Int64) {
    lock.lock()
    nowMs = value
    lock.unlock()
  }

  func advance(by deltaMs: Int64) {
    lock.lock()
    nowMs += deltaMs
    lock.unlock()
  }

  var nowProvider: () -> Int64 {
    { [weak self] in
      self?.now() ?? 0
    }
  }
}

/// Thread-safe deterministic pseudo-random source for repeatable tests.
/// @unchecked Sendable is safe here because all mutable state is guarded by `lock`.
final class DeterministicTestRandom: @unchecked Sendable {
  private let lock = NSLock()
  private var state: UInt64

  init(seed: UInt64) {
    self.state = seed == 0 ? 0xD00D_F00D_CAFE_BABE : seed
  }

  func nextUInt64() -> UInt64 {
    lock.lock()
    defer { lock.unlock() }
    state = 6364136223846793005 &* state &+ 1442695040888963407
    return state
  }

  func nextInt(upperBound: Int) -> Int {
    precondition(upperBound > 0)
    return Int(nextUInt64() % UInt64(upperBound))
  }
}

protocol TestSleeper: Sendable {
  func sleep(nanoseconds: UInt64) async throws
}

struct TaskSleeper: TestSleeper {
  func sleep(nanoseconds: UInt64) async throws {
    try await Task.sleep(nanoseconds: nanoseconds)
  }
}

actor DeterministicTestSleeper: TestSleeper {
  private var requestedDurationsNs: [UInt64] = []

  func sleep(nanoseconds: UInt64) async throws {
    requestedDurationsNs.append(nanoseconds)
  }

  func requestedDurations() -> [UInt64] {
    requestedDurationsNs
  }

  func reset() {
    requestedDurationsNs = []
  }
}
