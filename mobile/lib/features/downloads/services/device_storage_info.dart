import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Free bytes on the volume the on-device store writes to — the primitive
/// behind the ~1.5 GB free-space floor (spec §3/§3b).
///
/// `dart:io` has no cross-platform "bytes free" API, and this project adds
/// no new plugins for one; this reuses the existing native bridge channel
/// (`com.manhwamaniacs.reader/native`, see `core/platform/native_bridge.dart`)
/// with one more method, implemented directly in `MainActivity.kt` /
/// `AppDelegate.swift` — the same "no pod, no Gradle dependency" pattern the
/// spec sets for OCR (§4).
///
/// A separate class from [NativeBridge] on purpose: that abstraction is
/// Android-only (`_supported => Platform.isAndroid`) because volume-key
/// interception and `ActivityManager` memory stats only make sense there.
/// Free disk space matters on iOS too — arguably more, since a sideloaded
/// build has no way to prompt for more storage — so this checks both
/// platforms independently rather than widening `NativeBridge`'s gate (and
/// risking the volume-key/memory-info behaviour it already ships).
abstract class DeviceStorageInfo {
  /// Bytes free, or `null` when undeterminable (unsupported platform/OS
  /// version, or any platform-channel failure). Callers must have a sane
  /// fallback — see [DownloadQueueController]'s handling of `null`.
  Future<int?> freeSpaceBytes();
}

class PlatformDeviceStorageInfo implements DeviceStorageInfo {
  static const _channel = MethodChannel('com.manhwamaniacs.reader/native');

  bool get _supported => !kIsWeb && (Platform.isAndroid || Platform.isIOS);

  @override
  Future<int?> freeSpaceBytes() async {
    if (!_supported) return null;
    try {
      return await _channel.invokeMethod<int>('getFreeDiskSpace');
    } catch (_) {
      return null;
    }
  }
}

final deviceStorageInfoProvider = Provider<DeviceStorageInfo>(
  (_) => PlatformDeviceStorageInfo(),
  name: 'deviceStorageInfo',
);
