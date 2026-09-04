import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/core/platform/native_bridge.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// Whether the app asks the panel for its fastest refresh rate.
///
/// Default **on**. Android hands an app the display's default mode, and on
/// nearly every 90/120/144 Hz phone that default is 60 Hz; an app whose core
/// interaction is a continuous vertical scroll is exactly where that reads as
/// "laggy". The setting exists because the ask is not free — a pinned fast
/// mode keeps the panel refreshing at that rate whether or not anything is
/// moving, which costs battery.
///
/// Device-scoped rather than per-persona (unlike the palette and preset): it
/// describes the hardware in the user's hand, not a reading identity, so both
/// profiles on one phone share it.
class HighRefreshRateController extends Notifier<bool> {
  @override
  bool build() => ref.watch(preferencesProvider).highRefreshRate;

  Future<void> setEnabled(bool value) async {
    state = value;
    await ref.read(preferencesProvider).setHighRefreshRate(value);
  }
}

final highRefreshRateProvider =
    NotifierProvider<HighRefreshRateController, bool>(
  HighRefreshRateController.new,
  name: 'highRefreshRate',
);

/// The app's single owner of the window's display-mode preference.
///
/// Watched from `ManhwaManiacsApp` — the same idiom as
/// `profileHeaderSyncProvider` — so the preference is asserted once at startup
/// and re-asserted on every change, without any individual screen having to
/// remember to. One owner matters here: `preferredDisplayModeId` is a single
/// window attribute, and the last writer wins for the life of the window.
final highRefreshRateSyncProvider = Provider<void>(
  (ref) {
    final enabled = ref.watch(highRefreshRateProvider);
    // Fire-and-forget: the channel call is a one-way instruction to the
    // Activity and nothing in the tree waits on the result.
    final bridge = ref.read(nativeBridgeProvider);
    unawaited(bridge.setHighRefreshRateEnabled(enabled));
  },
  name: 'highRefreshRateSync',
);
