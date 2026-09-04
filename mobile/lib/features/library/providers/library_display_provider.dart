import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// Multiplier applied to the library grid's cover size. 1.0 = default columns
/// for the viewport; higher = larger covers / fewer columns. Persisted so the
/// user's preferred density survives restarts.
const double minLibraryCoverScale = 0.7;
const double maxLibraryCoverScale = 1.6;

class LibraryCoverScaleController extends Notifier<double> {
  /// Debounce for the preference write. Cancelled on rebuild/dispose; losing
  /// an in-flight write there costs one slider position, not any real state.
  Timer? _persist;

  @override
  double build() {
    ref.onDispose(() => _persist?.cancel());
    return ref
        .watch(preferencesProvider)
        .libraryCoverScale
        .clamp(minLibraryCoverScale, maxLibraryCoverScale);
  }

  /// Applies [value] immediately and remembers it once the drag settles.
  ///
  /// The slider calls this on every frame it moves, so persisting inline meant
  /// a SharedPreferences write per frame for the whole gesture — platform-
  /// channel I/O on the UI isolate, of which only the last value matters.
  void setScale(double value) {
    final clamped = value.clamp(minLibraryCoverScale, maxLibraryCoverScale);
    if (clamped == state) return;
    state = clamped;
    _persist?.cancel();
    _persist = Timer(const Duration(milliseconds: 250), () {
      ref.read(preferencesProvider).setLibraryCoverScale(clamped);
    });
  }
}

final libraryCoverScaleProvider =
    NotifierProvider<LibraryCoverScaleController, double>(
  LibraryCoverScaleController.new,
);
