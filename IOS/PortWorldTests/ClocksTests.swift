import Foundation
import XCTest
@testable import PortWorld

final class ClocksTests: XCTestCase {
  func testNowMsIsNonDecreasingAcrossRapidReads() {
    var previous = Clocks.nowMs()

    for _ in 0..<2_000 {
      let current = Clocks.nowMs()
      XCTAssertGreaterThanOrEqual(current, previous)
      previous = current
    }
  }

  func testNowMsRemainsWithinWallClockTolerance() {
    let observed = Clocks.nowMs()
    let wallClock = Int64(Date().timeIntervalSince1970 * 1000)
    let toleranceMs: Int64 = 2_000

    XCTAssertLessThanOrEqual(abs(observed - wallClock), toleranceMs)
  }
}
