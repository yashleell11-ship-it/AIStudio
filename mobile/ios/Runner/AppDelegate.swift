import Flutter
import UIKit
import Vision

// Same channel name/id the Android side registers
// (`com.manhwamaniacs.reader/native`) — iOS only ever implements
// `getFreeDiskSpace` on it today (volume-key interception and device-memory
// stats stay Android-only), so every other method falls through to
// `FlutterMethodNotImplemented`, which `NativeBridge` on the Dart side
// already treats as a safe no-op/`null` via its existing try/catch. Added
// for 1c-M3's on-device chapter store: the ~1.5 GB free-space floor needs a
// real number, and `dart:io` has no cross-platform "bytes free" API. No new
// pod — `URLResourceKey` is plain Foundation.
//
// 1c-M4 adds a second channel, `mm/ocr`, backed by Vision. It lives in this
// file rather than a new one on purpose: adding a source file to the Runner
// target means editing `Runner.xcodeproj/project.pbxproj`, and this build is
// signed and shipped by a cloud-Mac workflow no one here can dry-run — a
// malformed project file would break the only iOS pipeline the owner has.
// Vision itself is a system framework, so `Podfile.lock` (generated in CI)
// is untouched either way, which is the constraint spec §4 actually cares
// about.
@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private let nativeChannelName = "com.manhwamaniacs.reader/native"
  private let ocrChannelName = "mm/ocr"

  /// Mirrors `OCR_MAX_BOXES_PER_PAGE` in `backend/routes/ocr.py`. The Dart
  /// side caps too (`capOcrPagesForUpload`), but capping here as well keeps a
  /// pathological page from marshalling thousands of dictionaries across the
  /// channel only to have them thrown away a moment later.
  private let maxBoxesPerPage = 300

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)

    let messenger = engineBridge.pluginRegistry as! FlutterBinaryMessenger

    let channel = FlutterMethodChannel(
      name: nativeChannelName,
      binaryMessenger: messenger
    )
    channel.setMethodCallHandler { [weak self] call, result in
      switch call.method {
      case "getFreeDiskSpace":
        result(self?.readFreeDiskSpaceBytes())
      default:
        result(FlutterMethodNotImplemented)
      }
    }

    let ocrChannel = FlutterMethodChannel(
      name: ocrChannelName,
      binaryMessenger: messenger
    )
    ocrChannel.setMethodCallHandler { [weak self] call, result in
      self?.handleOcrCall(call, result: result)
    }
  }

  // Bytes free on the volume backing the app's Documents directory — the
  // same directory the blob store writes to (spec §3b), so this matches the
  // partition the free-space floor is actually protecting.
  private func readFreeDiskSpaceBytes() -> Int64? {
    guard let documentsUrl = FileManager.default.urls(
      for: .documentDirectory, in: .userDomainMask
    ).first else { return nil }

    let values = try? documentsUrl.resourceValues(
      forKeys: [.volumeAvailableCapacityForImportantUsageKey]
    )
    return values?.volumeAvailableCapacityForImportantUsage
  }

  // MARK: - mm/ocr

  private func handleOcrCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "isAvailable":
      // Unconditionally true: `VNRecognizeTextRequest` ships with iOS 13 and
      // Runner.xcodeproj sets IPHONEOS_DEPLOYMENT_TARGET = 13.0, so any
      // device that can install this build can run it. The Dart side's
      // capability gate still earns its keep — it catches the case this
      // cannot see, namely an installed build old enough that no handler is
      // registered on `mm/ocr` at all.
      result(true)

    case "engineId":
      result("vision")

    case "recognize":
      guard
        let args = call.arguments as? [String: Any],
        let paths = args["paths"] as? [String]
      else {
        result(FlutterError(
          code: "bad_arguments",
          message: "recognize expects { paths: [String] }",
          details: nil
        ))
        return
      }
      // Vision on a full-resolution manhwa page is hundreds of milliseconds
      // of work. Doing it on the platform thread would stall the whole UI —
      // the one thing spec §4 says a 60-page run must not do — so it runs on
      // a background queue and hops back to the main thread to reply, which
      // is where FlutterResult must be invoked.
      DispatchQueue.global(qos: .userInitiated).async { [weak self] in
        guard let self = self else {
          DispatchQueue.main.async { result([[String: Any]]()) }
          return
        }
        let pages = paths.map { self.recognizePage(atPath: $0) }
        DispatchQueue.main.async { result(pages) }
      }

    default:
      result(FlutterMethodNotImplemented)
    }
  }

  /// Recognizes one page image, returning the `{text, boxes}` map the Dart
  /// `PageText.fromChannel` expects. Never throws: an unreadable or
  /// undecodable file becomes an empty page so one bad blob costs its own
  /// page and not the other fifty-nine.
  private func recognizePage(atPath path: String) -> [String: Any] {
    // Each page decodes a full-resolution image; without an explicit pool the
    // autoreleased backing stores would pile up for the length of a chapter
    // run and get the app jetsammed on an older phone.
    return autoreleasepool { () -> [String: Any] in
      let emptyPage: [String: Any] = ["text": "", "boxes": [[String: Any]]()]

      guard
        let image = UIImage(contentsOfFile: path),
        let cgImage = image.cgImage
      else {
        return emptyPage
      }

      let request = VNRecognizeTextRequest()
      request.recognitionLevel = .accurate
      // Speech-bubble dialogue is ordinary prose, so the language model
      // meaningfully improves it — this is not receipt/serial-number OCR
      // where correction does more harm than good.
      request.usesLanguageCorrection = true

      let handler = VNImageRequestHandler(
        cgImage: cgImage,
        orientation: Self.cgOrientation(from: image.imageOrientation),
        options: [:]
      )
      do {
        try handler.perform([request])
      } catch {
        return emptyPage
      }

      // Written as a conditional downcast rather than relying on
      // `request.results` already being typed: the typed override only exists
      // in newer SDKs, and a redundant-cast warning on a new Xcode is a far
      // cheaper failure than a type error on an older one — this project
      // cannot compile Swift anywhere but the cloud-Mac runner.
      let observations = (request.results as? [VNRecognizedTextObservation]) ?? []
      var lines: [String] = []
      var boxes: [[String: Any]] = []

      for observation in observations {
        guard let candidate = observation.topCandidates(1).first else { continue }
        let text = candidate.string
        if text.isEmpty { continue }
        lines.append(text)

        if boxes.count < maxBoxesPerPage {
          let rect = observation.boundingBox
          boxes.append([
            "text": text,
            "x": Double(rect.origin.x),
            // Vision's normalized rects have a BOTTOM-left origin; the
            // channel contract (see `OcrTextBox`) is top-left so an iPhone
            // box and an Android box mean the same thing.
            "y": Double(1.0 - (rect.origin.y + rect.size.height)),
            "width": Double(rect.size.width),
            "height": Double(rect.size.height),
            "confidence": Double(candidate.confidence),
          ])
        }
      }

      let page: [String: Any] = [
        "text": lines.joined(separator: "\n"),
        "boxes": boxes,
      ]
      return page
    }
  }

  /// `CGImage` carries no orientation of its own, so a page saved with a
  /// non-`.up` EXIF orientation would be recognized sideways without this.
  private static func cgOrientation(
    from orientation: UIImage.Orientation
  ) -> CGImagePropertyOrientation {
    switch orientation {
    case .up: return .up
    case .upMirrored: return .upMirrored
    case .down: return .down
    case .downMirrored: return .downMirrored
    case .left: return .left
    case .leftMirrored: return .leftMirrored
    case .right: return .right
    case .rightMirrored: return .rightMirrored
    @unknown default: return .up
    }
  }
}
