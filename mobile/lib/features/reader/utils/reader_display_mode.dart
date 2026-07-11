import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_displaymode/flutter_displaymode.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';

/// A read-only view of the device's current and available display modes, used
/// by the diagnostics screen to verify the refresh-rate selector actually took
/// effect at the OS level.
class DisplayModeInfo {
  const DisplayModeInfo({
    required this.supported,
    required this.activeRefreshRate,
    required this.activeWidth,
    required this.activeHeight,
    required this.maxRefreshRate,
  });

  /// True when the platform exposes switchable display modes (Android only).
  final bool supported;

  /// Currently active physical refresh rate in Hz (0 when unknown).
  final double activeRefreshRate;

  /// Active physical resolution.
  final int activeWidth;
  final int activeHeight;

  /// Highest refresh rate the panel advertises — the device's capability.
  final double maxRefreshRate;

  static const DisplayModeInfo unsupported = DisplayModeInfo(
    supported: false,
    activeRefreshRate: 0,
    activeWidth: 0,
    activeHeight: 0,
    maxRefreshRate: 0,
  );
}

/// Applies a preferred physical display refresh rate while the reader is open.
///
/// Only Android exposes switchable display modes; every other platform (and
/// the test host) is a silent no-op, so the reader never touches a platform
/// channel there. Injected via [readerDisplayModeProvider] so widget tests can
/// override it with a fake.
abstract class ReaderDisplayMode {
  /// Request the display mode that best matches [rate].
  Future<void> apply(ReaderRefreshRate rate);

  /// Restore the system-managed automatic mode (called when leaving the reader).
  Future<void> reset();

  /// Read the active + supported display modes for diagnostics. Never throws.
  Future<DisplayModeInfo> describe();
}

class PlatformReaderDisplayMode implements ReaderDisplayMode {
  const PlatformReaderDisplayMode();

  bool get _supported => !kIsWeb && Platform.isAndroid;

  @override
  Future<void> apply(ReaderRefreshRate rate) async {
    if (!_supported) return;
    try {
      final target = rate.targetHz;
      if (target == null) {
        // Auto — let the platform pick the highest rate at the active size.
        await FlutterDisplayMode.setHighRefreshRate();
        return;
      }
      final modes = await FlutterDisplayMode.supported;
      final active = await FlutterDisplayMode.active;
      final best = pickMode(modes, active, target);
      if (best != null) {
        await FlutterDisplayMode.setPreferredMode(best);
      }
    } catch (_) {
      // DisplayMode is unavailable on some OEM ROMs / OS versions; degrade
      // silently rather than crashing the reader.
    }
  }

  @override
  Future<void> reset() async {
    if (!_supported) return;
    try {
      await FlutterDisplayMode.setPreferredMode(DisplayMode.auto);
    } catch (_) {
      // ignore — nothing to restore if the platform refused the request.
    }
  }

  @override
  Future<DisplayModeInfo> describe() async {
    if (!_supported) return DisplayModeInfo.unsupported;
    try {
      final active = await FlutterDisplayMode.active;
      final modes = await FlutterDisplayMode.supported;
      final maxRate = modes.isEmpty
          ? active.refreshRate
          : modes.map((m) => m.refreshRate).reduce((a, b) => a > b ? a : b);
      return DisplayModeInfo(
        supported: true,
        activeRefreshRate: active.refreshRate,
        activeWidth: active.width,
        activeHeight: active.height,
        maxRefreshRate: maxRate,
      );
    } catch (_) {
      return DisplayModeInfo.unsupported;
    }
  }
}

/// Chooses the supported [DisplayMode] whose refresh rate is closest to
/// [target] Hz while keeping the physical resolution unchanged (switching
/// resolution mid-session would force a full relayout). Ties prefer the higher
/// rate. Exposed for unit testing; returns ``null`` when nothing matches.
@visibleForTesting
DisplayMode? pickMode(
  List<DisplayMode> modes,
  DisplayMode active,
  double target,
) {
  final sameResolution = modes
      .where((m) => m.width == active.width && m.height == active.height)
      .toList();
  // Fall back to every concrete (non-auto, id != 0) mode if the active
  // resolution can't be matched (e.g. active reported as the auto entry).
  final candidates = sameResolution.isNotEmpty
      ? sameResolution
      : modes.where((m) => m.id != 0).toList();
  if (candidates.isEmpty) return null;

  candidates.sort((a, b) {
    final da = (a.refreshRate - target).abs();
    final db = (b.refreshRate - target).abs();
    if (da != db) return da.compareTo(db);
    return b.refreshRate.compareTo(a.refreshRate);
  });
  return candidates.first;
}

final readerDisplayModeProvider = Provider<ReaderDisplayMode>(
  (_) => const PlatformReaderDisplayMode(),
  name: 'readerDisplayMode',
);
