import Flutter
import UIKit

// Same channel name/id the Android side registers
// (`com.manhwamaniacs.reader/native`) — iOS only ever implements
// `getFreeDiskSpace` on it today (volume-key interception and device-memory
// stats stay Android-only), so every other method falls through to
// `FlutterMethodNotImplemented`, which `NativeBridge` on the Dart side
// already treats as a safe no-op/`null` via its existing try/catch. Added
// for 1c-M3's on-device chapter store: the ~1.5 GB free-space floor needs a
// real number, and `dart:io` has no cross-platform "bytes free" API. No new
// pod — `URLResourceKey` is plain Foundation.
@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private let nativeChannelName = "com.manhwamaniacs.reader/native"

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)

    let channel = FlutterMethodChannel(
      name: nativeChannelName,
      binaryMessenger: engineBridge.pluginRegistry as! FlutterBinaryMessenger
    )
    channel.setMethodCallHandler { [weak self] call, result in
      switch call.method {
      case "getFreeDiskSpace":
        result(self?.readFreeDiskSpaceBytes())
      default:
        result(FlutterMethodNotImplemented)
      }
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
}
