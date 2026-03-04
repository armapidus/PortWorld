import XCTest
@testable import PortWorld

final class ManualWakeWordEngineTests: XCTestCase {

  private var engine: ManualWakeWordEngine!

  override func setUp() {
    super.setUp()
    engine = ManualWakeWordEngine(defaultPhrase: "hey test")
  }

  override func tearDown() {
    engine = nil
    super.tearDown()
  }

  // MARK: - Listening state

  func testInitialStateIsNotListening() {
    XCTAssertFalse(engine.isListening)
  }

  func testStartListeningTogglesOn() {
    engine.startListening()
    XCTAssertTrue(engine.isListening)
  }

  func testStopListeningTogglesOff() {
    engine.startListening()
    engine.stopListening()
    XCTAssertFalse(engine.isListening)
  }

  func testStartStopCycle() {
    engine.startListening()
    XCTAssertTrue(engine.isListening)
    engine.stopListening()
    XCTAssertFalse(engine.isListening)
    engine.startListening()
    XCTAssertTrue(engine.isListening)
  }

  // MARK: - Manual trigger while listening

  func testTriggerWhileListeningFiresWakeDetected() {
    var received: WakeWordDetectionEvent?
    engine.onWakeDetected = { event in
      received = event
    }

    engine.startListening()
    engine.triggerManualWake(timestampMs: 1_000)

    XCTAssertNotNil(received)
    XCTAssertEqual(received?.wakePhrase, "hey test")
    XCTAssertEqual(received?.engine, "manual")
    XCTAssertEqual(received?.confidence, 1.0)
    XCTAssertGreaterThan(received?.timestampMs ?? 0, 0)
  }

  func testTriggerWithCustomPhraseAndConfidence() {
    var received: WakeWordDetectionEvent?
    engine.onWakeDetected = { event in
      received = event
    }

    engine.startListening()
    engine.triggerManualWake(wakePhrase: "hey port", timestampMs: 1_000, confidence: 0.95)

    XCTAssertEqual(received?.wakePhrase, "hey port")
    XCTAssertEqual(received?.confidence, 0.95)
  }

  func testTriggerWithCustomTimestamp() {
    var received: WakeWordDetectionEvent?
    engine.onWakeDetected = { event in
      received = event
    }

    engine.startListening()
    engine.triggerManualWake(timestampMs: 42_000)

    XCTAssertEqual(received?.timestampMs, 42_000)
  }

  // MARK: - Manual trigger while not listening

  func testTriggerWhileNotListeningFiresError() {
    var receivedError: Error?
    engine.onError = { error in
      receivedError = error
    }

    engine.triggerManualWake(timestampMs: 1_000)

    XCTAssertNotNil(receivedError)
    XCTAssertTrue(receivedError is WakeWordEngineError)
  }

  func testTriggerWhileNotListeningDoesNotFireWakeDetected() {
    engine.onWakeDetected = { _ in
      XCTFail("onWakeDetected should not fire when not listening")
    }
    engine.onError = { _ in } // absorb error

    engine.triggerManualWake(timestampMs: 1_000)
  }

  // MARK: - processPCMFrame (no-op for v4)

  func testProcessPCMFrameDoesNotCrash() {
    engine.startListening()
    engine.processPCMFrame([0, 1, -1, 32767, -32768], timestampMs: 1000)
    // No assertion needed — verify no crash
  }

  func testProcessPCMFrameDoesNotFireWakeDetected() {
    engine.onWakeDetected = { _ in
      XCTFail("processPCMFrame should never trigger wake in manual engine")
    }
    engine.startListening()
    engine.processPCMFrame([100, 200, 300], timestampMs: 1000)
  }

  func testProcessPCMFrameWhileNotListeningDoesNotCrash() {
    engine.processPCMFrame([0, 0, 0], timestampMs: 500)
    // No assertion — just verify no crash
  }

  // MARK: - Default phrase

  func testDefaultPhraseUsedWhenNilProvided() {
    var received: WakeWordDetectionEvent?
    engine.onWakeDetected = { event in
      received = event
    }

    engine.startListening()
    engine.triggerManualWake(wakePhrase: nil, timestampMs: 1_000)

    XCTAssertEqual(received?.wakePhrase, "hey test")
  }
}
