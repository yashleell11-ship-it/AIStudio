import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/ocr/models/ocr_coverage.dart';
import 'package:manhwamaniacs/features/ocr/repositories/ocr_repository.dart';
import 'package:manhwamaniacs/features/ocr/repositories/ocr_repository_impl.dart';
import 'package:manhwamaniacs/features/ocr/services/ocr_engine.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

final ocrRepositoryProvider = Provider<OcrRepository>(
  (ref) => OcrRepositoryImpl(ref.watch(dioProvider)),
  name: 'ocrRepository',
);

/// Injected rather than constructed at each call site so tests (and the
/// desktop debug build) can substitute a fake without touching a channel.
final ocrEngineProvider = Provider<OcrEngine>(
  (ref) => const MethodChannelOcrEngine(),
  name: 'ocrEngine',
);

/// Whether this device can run OCR at all — the single gate every OCR
/// affordance in the app hangs off (spec §4: "absent/failed platform impl →
/// feature hidden").
///
/// A `Provider`, not `autoDispose`: the answer cannot change during a run of
/// the app, and keeping it alive means the More screen and the Downloads
/// screen don't each re-ask the channel on every rebuild.
final ocrAvailableProvider = FutureProvider<bool>(
  (ref) async {
    try {
      return await ref.watch(ocrEngineProvider).isAvailable();
    } catch (_) {
      return false;
    }
  },
  name: 'ocrAvailable',
);

/// Convenience read of [ocrAvailableProvider] for widgets that only want to
/// show or hide something: unresolved and errored both mean "hide", because
/// an OCR button that appears a frame late is far better than one that
/// appears and then fails.
final ocrFeatureVisibleProvider = Provider<bool>(
  (ref) => ref.watch(ocrAvailableProvider).valueOrNull ?? false,
  name: 'ocrFeatureVisible',
);

/// `GET /ocr/coverage` for one series — drives the "OCR this chapter" vs
/// "already OCR'd" affordance. Errors surface as [OcrCoverage.empty] rather
/// than an error state: an unreachable server should leave the OCR button
/// offered (running it again is harmless — the backend upserts), never leave
/// the row showing a failure the user cannot act on.
final ocrCoverageProvider = FutureProvider.autoDispose
    .family<OcrCoverage, SeriesIdentity>((ref, series) async {
  final result = await ref.watch(ocrRepositoryProvider).coverage(
        sourceId: series.sourceId,
        seriesKey: series.seriesKey,
      );
  return result.fold(ok: (coverage) => coverage, err: (_) => OcrCoverage.empty);
});
