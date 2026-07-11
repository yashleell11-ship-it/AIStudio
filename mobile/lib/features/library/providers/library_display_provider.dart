import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// Multiplier applied to the library grid's cover size. 1.0 = default columns
/// for the viewport; higher = larger covers / fewer columns. Persisted so the
/// user's preferred density survives restarts.
const double minLibraryCoverScale = 0.7;
const double maxLibraryCoverScale = 1.6;

class LibraryCoverScaleController extends Notifier<double> {
  @override
  double build() => ref
      .watch(preferencesProvider)
      .libraryCoverScale
      .clamp(minLibraryCoverScale, maxLibraryCoverScale);

  Future<void> setScale(double value) async {
    final clamped = value.clamp(minLibraryCoverScale, maxLibraryCoverScale);
    state = clamped;
    await ref.read(preferencesProvider).setLibraryCoverScale(clamped);
  }
}

final libraryCoverScaleProvider =
    NotifierProvider<LibraryCoverScaleController, double>(
  LibraryCoverScaleController.new,
);
