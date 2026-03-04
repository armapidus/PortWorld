import SnapshotTesting
import SwiftUI
import UIKit
import XCTest
@testable import PortWorld

@MainActor
final class SnapshotTests: XCTestCase {
  private var shouldRecordSnapshots: Bool {
    ProcessInfo.processInfo.environment["RECORD_SNAPSHOTS"] == "1"
  }

  func testCircleButton_iconOnly_lightAndDark() {
    assertLightAndDarkSnapshot(
      name: "CircleButton.iconOnly",
      size: CGSize(width: 140, height: 140)
    ) {
      CircleButton(icon: "camera.fill", text: nil, action: {})
    }
  }

  func testCircleButton_withText_lightAndDark() {
    assertLightAndDarkSnapshot(
      name: "CircleButton.withText",
      size: CGSize(width: 140, height: 140)
    ) {
      CircleButton(icon: "waveform", text: "Wake", action: {})
    }
  }

  func testCustomButton_primaryAndDestructive_lightAndDark() {
    assertLightAndDarkSnapshot(
      name: "CustomButton.styles",
      size: CGSize(width: 360, height: 190)
    ) {
      VStack(spacing: 16) {
        CustomButton(title: "Activate assistant", style: .primary, isDisabled: false, action: {})
        CustomButton(title: "Deactivate assistant", style: .destructive, isDisabled: false, action: {})
        CustomButton(title: "Disabled action", style: .primary, isDisabled: true, action: {})
      }
    }
  }

  func testTipRow_variants_lightAndDark() {
    assertLightAndDarkSnapshot(
      name: "TipRowView.variants",
      size: CGSize(width: 390, height: 220)
    ) {
      VStack(alignment: .leading, spacing: 18) {
        TipRowView(
          resource: .cameraAccessIcon,
          title: "Microphone Access",
          text: "Allow microphone to stream your voice in live sessions.",
          iconColor: .appPrimary,
          titleColor: .primary,
          textColor: .secondary
        )

        TipRowView(
          resource: .smartGlassesIcon,
          text: "Keep glasses connected and internet available for realtime responses.",
          iconColor: .appPrimary,
          titleColor: .primary,
          textColor: .secondary
        )
      }
      .padding(.vertical, 8)
    }
  }

  func testPhotoPreviewView_lightAndDark() {
    let photo = makeSamplePhoto()
    assertLightAndDarkSnapshot(
      name: "PhotoPreviewView.default",
      size: CGSize(width: 390, height: 844)
    ) {
      PhotoPreviewView(photo: photo, onDismiss: {})
    }
  }

  private func assertLightAndDarkSnapshot<V: View>(
    name: String,
    size: CGSize,
    @ViewBuilder content: () -> V,
    file: StaticString = #filePath,
    testName: String = #function,
    line: UInt = #line
  ) {
    let wrapped = content()
      .padding(16)
      .frame(width: size.width, height: size.height, alignment: .topLeading)
      .background(Color(.systemBackground))

    let host = UIHostingController(rootView: wrapped)
    host.view.frame = CGRect(origin: .zero, size: size)

    assertSnapshot(
      of: host.view,
      as: .image(size: size, traits: .init(userInterfaceStyle: .light)),
      named: "\(name).light",
      record: shouldRecordSnapshots,
      file: file,
      testName: testName,
      line: line
    )

    assertSnapshot(
      of: host.view,
      as: .image(size: size, traits: .init(userInterfaceStyle: .dark)),
      named: "\(name).dark",
      record: shouldRecordSnapshots,
      file: file,
      testName: testName,
      line: line
    )
  }

  private func makeSamplePhoto() -> UIImage {
    let size = CGSize(width: 1200, height: 900)
    let renderer = UIGraphicsImageRenderer(size: size)
    return renderer.image { context in
      let bounds = CGRect(origin: .zero, size: size)
      let colors = [UIColor.systemBlue.cgColor, UIColor.systemTeal.cgColor] as CFArray
      let space = CGColorSpaceCreateDeviceRGB()
      let locations: [CGFloat] = [0, 1]
      if let gradient = CGGradient(colorsSpace: space, colors: colors, locations: locations) {
        context.cgContext.drawLinearGradient(
          gradient,
          start: CGPoint(x: 0, y: 0),
          end: CGPoint(x: size.width, y: size.height),
          options: []
        )
      }

      let inset = bounds.insetBy(dx: 120, dy: 120)
      context.cgContext.setStrokeColor(UIColor.white.withAlphaComponent(0.75).cgColor)
      context.cgContext.setLineWidth(14)
      context.cgContext.stroke(inset)
    }
  }
}
