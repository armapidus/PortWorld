import XCTest
@testable import MetaCollectLuigi

final class EventLoggerTests: XCTestCase {

  // MARK: - Sink emission

  func testLogEmitsValidJsonToSink() {
    var lines: [String] = []
    let logger = EventLogger(sink: { lines.append($0) })

    logger.log(name: "test.event", sessionID: "sess_1", fields: ["key": .string("val")])

    XCTAssertEqual(lines.count, 1)

    guard let data = lines.first?.data(using: .utf8),
          let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      XCTFail("Sink output is not valid JSON")
      return
    }

    XCTAssertEqual(json["name"] as? String, "test.event")
    XCTAssertEqual(json["session_id"] as? String, "sess_1")
    XCTAssertNotNil(json["ts_ms"])
  }

  func testLogWithQueryIdIncludesQueryId() {
    var lines: [String] = []
    let logger = EventLogger(sink: { lines.append($0) })

    logger.log(name: "query.started", sessionID: "sess_1", queryID: "q_42")

    guard let data = lines.first?.data(using: .utf8),
          let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      XCTFail("Sink output is not valid JSON")
      return
    }

    XCTAssertEqual(json["query_id"] as? String, "q_42")
  }

  func testLogWithoutQueryIdHasNullQueryId() {
    var lines: [String] = []
    let logger = EventLogger(sink: { lines.append($0) })

    logger.log(name: "session.activated", sessionID: "sess_1")

    guard let data = lines.first?.data(using: .utf8),
          let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      XCTFail("Sink output is not valid JSON")
      return
    }

    // query_id should be null or absent
    let queryId = json["query_id"]
    XCTAssertTrue(queryId == nil || queryId is NSNull)
  }

  func testLogWithExplicitTimestamp() {
    var lines: [String] = []
    let logger = EventLogger(sink: { lines.append($0) })

    logger.log(name: "timed", sessionID: "s", tsMs: 1234567890)

    guard let data = lines.first?.data(using: .utf8),
          let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      XCTFail("Sink output is not valid JSON")
      return
    }

    XCTAssertEqual(json["ts_ms"] as? Int, 1234567890)
  }

  func testLogMultipleEventsEmitsMultipleLines() {
    var lines: [String] = []
    let logger = EventLogger(sink: { lines.append($0) })

    logger.log(name: "e1", sessionID: "s")
    logger.log(name: "e2", sessionID: "s")
    logger.log(name: "e3", sessionID: "s")

    XCTAssertEqual(lines.count, 3)
  }

  // MARK: - recentEvents

  func testRecentEventsReturnsLoggedEvents() {
    let logger = EventLogger(sink: { _ in })

    logger.log(name: "e1", sessionID: "s")
    logger.log(name: "e2", sessionID: "s")
    logger.log(name: "e3", sessionID: "s")

    let recent = logger.recentEvents(limit: 10)
    XCTAssertEqual(recent.count, 3)
    XCTAssertEqual(recent[0].name, "e1")
    XCTAssertEqual(recent[1].name, "e2")
    XCTAssertEqual(recent[2].name, "e3")
  }

  func testRecentEventsRespectsLimit() {
    let logger = EventLogger(sink: { _ in })

    for i in 0..<10 {
      logger.log(name: "event_\(i)", sessionID: "s")
    }

    let recent = logger.recentEvents(limit: 3)
    XCTAssertEqual(recent.count, 3)
    // Should return the last 3 events
    XCTAssertEqual(recent[0].name, "event_7")
    XCTAssertEqual(recent[1].name, "event_8")
    XCTAssertEqual(recent[2].name, "event_9")
  }

  func testRecentEventsWithZeroLimitReturnsEmpty() {
    let logger = EventLogger(sink: { _ in })
    logger.log(name: "e", sessionID: "s")

    XCTAssertTrue(logger.recentEvents(limit: 0).isEmpty)
  }

  // MARK: - Retention / pruning

  func testPrunesOldestEventsWhenCapReached() {
    let logger = EventLogger(maxRetainedEvents: 3, sink: { _ in })

    logger.log(name: "a", sessionID: "s")
    logger.log(name: "b", sessionID: "s")
    logger.log(name: "c", sessionID: "s")
    logger.log(name: "d", sessionID: "s") // should evict "a"

    let events = logger.recentEvents(limit: 10)
    XCTAssertEqual(events.count, 3)
    XCTAssertEqual(events[0].name, "b")
    XCTAssertEqual(events[1].name, "c")
    XCTAssertEqual(events[2].name, "d")
  }

  func testRetentionAtExactCapDoesNotPrune() {
    let logger = EventLogger(maxRetainedEvents: 3, sink: { _ in })

    logger.log(name: "a", sessionID: "s")
    logger.log(name: "b", sessionID: "s")
    logger.log(name: "c", sessionID: "s")

    let events = logger.recentEvents(limit: 10)
    XCTAssertEqual(events.count, 3)
    XCTAssertEqual(events[0].name, "a")
  }

  // MARK: - clear

  func testClearRemovesAllEvents() {
    let logger = EventLogger(sink: { _ in })

    logger.log(name: "e1", sessionID: "s")
    logger.log(name: "e2", sessionID: "s")

    logger.clear()

    XCTAssertTrue(logger.recentEvents(limit: 100).isEmpty)
  }

  func testClearThenLogStartsFresh() {
    let logger = EventLogger(sink: { _ in })

    logger.log(name: "old", sessionID: "s")
    logger.clear()
    logger.log(name: "new", sessionID: "s")

    let events = logger.recentEvents(limit: 10)
    XCTAssertEqual(events.count, 1)
    XCTAssertEqual(events[0].name, "new")
  }

  // MARK: - Fields serialization

  func testFieldsAreIncludedInJson() {
    var lines: [String] = []
    let logger = EventLogger(sink: { lines.append($0) })

    logger.log(
      name: "with_fields",
      sessionID: "s",
      fields: [
        "count": .number(42),
        "active": .bool(true),
        "label": .string("test"),
      ]
    )

    guard let data = lines.first?.data(using: .utf8),
          let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let fields = json["fields"] as? [String: Any]
    else {
      XCTFail("Could not parse fields from JSON")
      return
    }

    XCTAssertEqual(fields["count"] as? Double, 42)
    XCTAssertEqual(fields["active"] as? Bool, true)
    XCTAssertEqual(fields["label"] as? String, "test")
  }

  func testEmptyFieldsSerializedAsEmptyObject() {
    var lines: [String] = []
    let logger = EventLogger(sink: { lines.append($0) })

    logger.log(name: "no_fields", sessionID: "s", fields: [:])

    guard let data = lines.first?.data(using: .utf8),
          let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let fields = json["fields"] as? [String: Any]
    else {
      XCTFail("Could not parse JSON")
      return
    }

    XCTAssertTrue(fields.isEmpty)
  }

  // MARK: - AppEvent direct logging

  func testLogAppEventDirectly() {
    var lines: [String] = []
    let logger = EventLogger(sink: { lines.append($0) })

    let event = AppEvent(
      name: "direct.event",
      sessionID: "sess_direct",
      queryID: "q_direct",
      tsMs: 77777,
      fields: ["x": .number(1)]
    )

    logger.log(event)

    XCTAssertEqual(lines.count, 1)

    guard let data = lines.first?.data(using: .utf8),
          let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      XCTFail("Not valid JSON")
      return
    }

    XCTAssertEqual(json["name"] as? String, "direct.event")
    XCTAssertEqual(json["session_id"] as? String, "sess_direct")
    XCTAssertEqual(json["query_id"] as? String, "q_direct")
    XCTAssertEqual(json["ts_ms"] as? Int, 77777)
  }
}
