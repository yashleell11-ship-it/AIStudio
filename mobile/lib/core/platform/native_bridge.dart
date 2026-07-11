import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Direction requested by a hardware volume-key press.
enum VolumeKeyDirection { up, down }

/// Real device memory, as reported by Android's `ActivityManager`.
class DeviceMemoryInfo {
  const DeviceMemoryInfo({
    required this.totalBytes,
    required this.availableBytes,
    required this.lowMemory,
  });

  final int totalBytes;
  final int availableBytes;
  final bool lowMemory;
}

/// Bridges the small bits of native functionality Flutter can't reach on its
/// own: intercepting hardware volume keys (must happen in the native
/// Activity, before the OS shows its volume UI) and real device memory
/// stats (to size the reader's image cache relative to the device).
///
/// Every platform other than Android — and the test host — is a silent
/// no-op, matching [ReaderDisplayMode]/[ReaderWakelock]: injected via
/// [nativeBridgeProvider] so widget tests never touch a real platform channel.
abstract class NativeBridge {
  /// Enable/disable volume-key interception. Call with `true` only while the
  /// reader is open and the user's "volume key navigation" setting is on;
  /// `false` otherwise so every other screen keeps normal volume behaviour.
  Future<void> setVolumeKeyNavEnabled(bool enabled);

  /// Fires once per physical volume-key press while interception is enabled.
  /// Never emits on platforms without native support.
  Stream<VolumeKeyDirection> get volumeKeyEvents;

  /// Real device memory stats, or `null` wherever unsupported or on any
  /// platform-channel failure — callers must have a sane fallback.
  Future<DeviceMemoryInfo?> getDeviceMemoryInfo();
}

class PlatformNativeBridge implements NativeBridge {
  PlatformNativeBridge() {
    if (_supported) {
      _channel.setMethodCallHandler(_handleMethodCall);
    }
  }

  static const _channel = MethodChannel('com.manhwamaniacs.app/native');

  bool get _supported => !kIsWeb && Platform.isAndroid;

  final _volumeKeyController = StreamController<VolumeKeyDirection>.broadcast();

  @override
  Stream<VolumeKeyDirection> get volumeKeyEvents => _volumeKeyController.stream;

  Future<void> _handleMethodCall(MethodCall call) async {
    switch (call.method) {
      case 'onVolumeUp':
        _volumeKeyController.add(VolumeKeyDirection.up);
      case 'onVolumeDown':
        _volumeKeyController.add(VolumeKeyDirection.down);
    }
  }

  @override
  Future<void> setVolumeKeyNavEnabled(bool enabled) async {
    if (!_supported) return;
    try {
      await _channel.invokeMethod<void>('setVolumeKeyNavEnabled', enabled);
    } catch (_) {
      // No native listener (unsupported OS version/build) — volume keys
      // just behave normally, which is a safe degrade.
    }
  }

  @override
  Future<DeviceMemoryInfo?> getDeviceMemoryInfo() async {
    if (!_supported) return null;
    try {
      final result =
          await _channel.invokeMethod<Map<Object?, Object?>>('getDeviceMemoryInfo');
      final total = result?['totalMem'];
      final avail = result?['availMem'];
      if (total is! int || avail is! int) return null;
      return DeviceMemoryInfo(
        totalBytes: total,
        availableBytes: avail,
        lowMemory: result?['lowMemory'] == true,
      );
    } catch (_) {
      return null;
    }
  }
}

final nativeBridgeProvider = Provider<NativeBridge>(
  (_) => PlatformNativeBridge(),
  name: 'nativeBridge',
);
