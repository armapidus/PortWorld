import XCTest
@testable import MetaCollectLuigi

final class QueryEndpointDetectorTests: XCTestCase {

  private var detector: QueryEndpointDetector!

  override func setUp() {
    super.setUp()
    // Short timeout + fast check interval for responsive tests
    detector = QueryEndpointDetector(
      silenceTimeoutMs: 300,
      checkIntervalMs: 50,
      callbackQueue: .main
    )
  }

  override func tearDown() {
    detector = nil
    super.tearDown()
  }

  // MARK: - beginQuery

  func testBeginQueryEmitsStartedEvent() {
    let exp = expectation(description: "onQueryStarted fires")

    detector.onQueryStarted = { event in
      XCTAssertTrue(event.queryId.hasPrefix("query_"))
      XCTAssertGreaterThan(event.startedAtMs, 0)
      exp.fulfill()
    }

    detector.beginQuery()
    waitForExpectations(timeout: 1)
  }

  func testBeginQueryWithCustomId() {
    let exp = expectation(description: "onQueryStarted with custom ID")

    detector.onQueryStarted = { event in
      XCTAssertEqual(event.queryId, "test_q_42")
      exp.fulfill()
    }

    detector.beginQuery(queryId: "test_q_42")
    waitForExpectations(timeout: 1)
  }

  func testDoubleBeginQueryIsIgnored() {
    var startCount = 0
    let exp = expectation(description: "only first beginQuery fires")

    detector.onQueryStarted = { event in
      startCount += 1
      XCTAssertEqual(event.queryId, "first")
      exp.fulfill()
    }

    detector.beginQuery(queryId: "first")
    detector.beginQuery(queryId: "second") // should be ignored

    waitForExpectations(timeout: 1)

    // Wait a bit longer to ensure no spurious second callback
    let noExtra = expectation(description: "no extra start")
    noExtra.isInverted = true
    waitForExpectations(timeout: 0.3)
    XCTAssertEqual(startCount, 1)
  }

  // MARK: - Silence timeout

  func testSilenceTimeoutFiresEndedEvent() {
    let endExp = expectation(description: "onQueryEnded fires")

    detector.onQueryEnded = { event in
      XCTAssertEqual(event.reason, .silenceTimeout)
      XCTAssertGreaterThan(event.durationMs, 0)
      endExp.fulfill()
    }

    detector.beginQuery()
    waitForExpectations(timeout: 2)
  }

  func testSpeechActivityDelaysTimeout() {
    let endExp = expectation(description: "onQueryEnded delayed by speech")

    detector.onQueryEnded = { event in
      // Duration should be >= ~400ms (200ms speech feed + 300ms timeout)
      // Allow tolerance for timer granularity
      XCTAssertGreaterThanOrEqual(event.durationMs, 250)
      XCTAssertEqual(event.reason, .silenceTimeout)
      endExp.fulfill()
    }

    detector.beginQuery()

    // Feed speech activity at 200ms to push the timeout window
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
      self.detector.recordSpeechActivity()
    }

    waitForExpectations(timeout: 3)
  }

  // MARK: - forceEnd

  func testForceEndEmitsManualStopReason() {
    let startExp = expectation(description: "started")
    let endExp = expectation(description: "ended with manualStop")

    detector.onQueryStarted = { _ in startExp.fulfill() }
    detector.onQueryEnded = { event in
      XCTAssertEqual(event.reason, .manualStop)
      endExp.fulfill()
    }

    detector.beginQuery()
    wait(for: [startExp], timeout: 1)
    detector.forceEnd()
    wait(for: [endExp], timeout: 1)
  }

  // MARK: - reset

  func testResetWithNoActiveQueryIsNoOp() {
    detector.onQueryEnded = { _ in
      XCTFail("onQueryEnded should not fire when no query is active")
    }

    detector.reset()

    let noCallback = expectation(description: "no callback")
    noCallback.isInverted = true
    waitForExpectations(timeout: 0.5)
  }

  func testResetWhileActiveEmitsResetReason() {
    let startExp = expectation(description: "started")
    let endExp = expectation(description: "ended with reset reason")

    detector.onQueryStarted = { _ in startExp.fulfill() }
    detector.onQueryEnded = { event in
      XCTAssertEqual(event.reason, .reset)
      endExp.fulfill()
    }

    detector.beginQuery()
    wait(for: [startExp], timeout: 1)
    detector.reset()
    wait(for: [endExp], timeout: 1)
  }

  // MARK: - isQueryActive

  func testIsQueryActiveReflectsLifecycle() {
    XCTAssertFalse(detector.isQueryActive)

    let startExp = expectation(description: "started")
    detector.onQueryStarted = { _ in startExp.fulfill() }
    detector.beginQuery()
    wait(for: [startExp], timeout: 1)
    XCTAssertTrue(detector.isQueryActive)

    let endExp = expectation(description: "ended")
    detector.onQueryEnded = { _ in endExp.fulfill() }
    detector.forceEnd()
    wait(for: [endExp], timeout: 1)
    XCTAssertFalse(detector.isQueryActive)
  }

  // MARK: - Duration calculation

  func testEndedEventHasValidDuration() {
    let endExp = expectation(description: "ended with valid duration")
    let fixedStart: Int64 = 1_000_000

    detector.onQueryEnded = { event in
      XCTAssertEqual(event.startedAtMs, fixedStart)
      XCTAssertGreaterThanOrEqual(event.endedAtMs, fixedStart)
      XCTAssertEqual(event.durationMs, event.endedAtMs - event.startedAtMs)
      endExp.fulfill()
    }

    detector.beginQuery(queryId: "dur_test", startedAtMs: fixedStart)
    // Let silence timeout fire
    waitForExpectations(timeout: 2)
  }

  // MARK: - Speech activity ping callback

  func testSpeechActivityPingCallbackFires() {
    let startExp = expectation(description: "started")
    let pingExp = expectation(description: "speech ping received")

    detector.onQueryStarted = { _ in startExp.fulfill() }
    detector.onSpeechActivityPing = { queryId, timestampMs in
      XCTAssertEqual(queryId, "ping_test")
      XCTAssertGreaterThan(timestampMs, 0)
      pingExp.fulfill()
    }

    detector.beginQuery(queryId: "ping_test")
    wait(for: [startExp], timeout: 1)
    detector.recordSpeechActivity()
    wait(for: [pingExp], timeout: 1)
  }
}
