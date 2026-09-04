import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/ocr/controllers/ocr_run_controller.dart';
import 'package:manhwamaniacs/features/ocr/models/ocr_coverage.dart';
import 'package:manhwamaniacs/features/ocr/models/page_text.dart';
import 'package:manhwamaniacs/features/ocr/providers/ocr_providers.dart';
import 'package:manhwamaniacs/features/ocr/services/ocr_engine.dart';
import 'package:manhwamaniacs/features/ocr/widgets/ocr_chapter_action.dart';
import 'package:manhwamaniacs/features/ocr/widgets/ocr_run_banner.dart';

/// Spec §4's "absent/failed platform impl → feature hidden" is a UI promise as
/// much as a plumbing one, so these drive the two widgets that keep it.
class _FakeOcrEngine implements OcrEngine {
  _FakeOcrEngine({required this.available});

  final bool available;

  @override
  Future<bool> isAvailable() async => available;

  @override
  Future<String> engineId() async => 'fake';

  @override
  Future<List<PageText>> recognize(
    List<String> imagePaths, {
    int startPage = 1,
  }) async =>
      const [];
}

/// An engine that throws rather than answering — a corrupt registration, or a
/// platform whose OCR framework is simply gone.
class _ThrowingOcrEngine implements OcrEngine {
  @override
  Future<bool> isAvailable() async => throw StateError('no engine');

  @override
  Future<String> engineId() async => throw StateError('no engine');

  @override
  Future<List<PageText>> recognize(
    List<String> imagePaths, {
    int startPage = 1,
  }) async =>
      throw StateError('no engine');
}

class _FixedRunController extends OcrRunController {
  _FixedRunController(this._state);
  final OcrRunState _state;

  @override
  OcrRunState build() => _state;
}

SavedChapter _chapter({
  DownloadChapterState state = DownloadChapterState.complete,
}) =>
    SavedChapter(
      rowId: 1,
      scopeId: 'u1p1',
      sourceId: 'asura',
      seriesKey: 'solo-leveling',
      chapterKey: '1',
      chapterNumber: 1,
      title: null,
      seriesTitle: 'Solo Leveling',
      pageCount: 20,
      bytes: 1024,
      state: state,
      pinned: false,
      readAt: null,
      createdAt: DateTime.utc(2026),
      retryCount: 0,
      error: null,
    );

void main() {
  Future<void> pump(
    WidgetTester tester,
    Widget child, {
    List<Override> overrides = const [],
  }) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: overrides,
        child: MaterialApp(home: Scaffold(body: child)),
      ),
    );
    // Twice: `ocrAvailableProvider` is a FutureProvider, so the first frame
    // is always "unresolved", which reads as hidden.
    await tester.pump();
    await tester.pump();
  }

  group('capability gating', () {
    testWidgets('the chapter action is absent without a platform engine',
        (tester) async {
      await pump(
        tester,
        OcrChapterAction(chapter: _chapter()),
        overrides: [
          ocrEngineProvider.overrideWithValue(_FakeOcrEngine(available: false)),
        ],
      );

      expect(find.byType(IconButton), findsNothing);
    });

    testWidgets('an engine that throws hides the action, it does not crash',
        (tester) async {
      await pump(
        tester,
        OcrChapterAction(chapter: _chapter()),
        overrides: [ocrEngineProvider.overrideWithValue(_ThrowingOcrEngine())],
      );

      expect(tester.takeException(), isNull);
      expect(find.byType(IconButton), findsNothing);
    });

    testWidgets('the action appears once an engine reports available',
        (tester) async {
      await pump(
        tester,
        OcrChapterAction(chapter: _chapter()),
        overrides: [
          ocrEngineProvider.overrideWithValue(_FakeOcrEngine(available: true)),
          ocrCoverageProvider.overrideWith((ref, series) async => OcrCoverage.empty),
        ],
      );

      expect(find.byTooltip('Extract text (OCR)'), findsOneWidget);
    });

    testWidgets('a chapter that is not fully downloaded gets no action',
        (tester) async {
      // OCR reads page files off disk; a queued chapter has none, and
      // downloading pages *in order to* OCR them is explicitly not the deal.
      await pump(
        tester,
        OcrChapterAction(chapter: _chapter(state: DownloadChapterState.queued)),
        overrides: [
          ocrEngineProvider.overrideWithValue(_FakeOcrEngine(available: true)),
        ],
      );

      expect(find.byType(IconButton), findsNothing);
    });
  });

  group('coverage affordance', () {
    testWidgets('a covered chapter offers a redo, not a fresh extraction',
        (tester) async {
      await pump(
        tester,
        OcrChapterAction(chapter: _chapter()),
        overrides: [
          ocrEngineProvider.overrideWithValue(_FakeOcrEngine(available: true)),
          ocrCoverageProvider.overrideWith(
            (ref, series) async => const OcrCoverage(
              sourceId: 'asura',
              seriesKey: 'solo-leveling',
              wordCountByChapterKey: {'1': 812},
            ),
          ),
        ],
      );

      expect(
        find.byTooltip('Text already extracted — tap to redo'),
        findsOneWidget,
      );
    });

    testWidgets('a zero-word row counts as not covered', (tester) async {
      // The ingest service refuses to overwrite a good transcript with an
      // empty one, so a 0-word row is a failed contribution, not a done one.
      await pump(
        tester,
        OcrChapterAction(chapter: _chapter()),
        overrides: [
          ocrEngineProvider.overrideWithValue(_FakeOcrEngine(available: true)),
          ocrCoverageProvider.overrideWith(
            (ref, series) async => const OcrCoverage(
              sourceId: 'asura',
              seriesKey: 'solo-leveling',
              wordCountByChapterKey: {'1': 0},
            ),
          ),
        ],
      );

      expect(find.byTooltip('Extract text (OCR)'), findsOneWidget);
    });
  });

  group('run banner', () {
    testWidgets('collapses entirely when idle', (tester) async {
      await pump(tester, const OcrRunBanner());

      expect(find.byType(Text), findsNothing);
    });

    testWidgets('reports page progress and offers a cancel', (tester) async {
      await pump(
        tester,
        const OcrRunBanner(),
        overrides: [
          ocrRunControllerProvider.overrideWith(
            () => _FixedRunController(
              const OcrRunState(
                phase: OcrRunPhase.recognizing,
                completedPages: 7,
                totalPages: 20,
              ),
            ),
          ),
        ],
      );

      expect(find.text('Extracting text — page 7 of 20'), findsOneWidget);
      expect(find.byKey(const Key('ocr-cancel')), findsOneWidget);
      final bar = tester.widget<LinearProgressIndicator>(
        find.byType(LinearProgressIndicator),
      );
      expect(bar.value, closeTo(0.35, 0.001));
    });

    testWidgets('shows the real failure reason, not a generic one',
        (tester) async {
      await pump(
        tester,
        const OcrRunBanner(),
        overrides: [
          ocrRunControllerProvider.overrideWith(
            () => _FixedRunController(
              const OcrRunState(
                phase: OcrRunPhase.failed,
                message: 'Download this chapter before running OCR on it.',
              ),
            ),
          ),
        ],
      );

      expect(
        find.text('Download this chapter before running OCR on it.'),
        findsOneWidget,
      );
      expect(find.byKey(const Key('ocr-cancel')), findsNothing);
    });

    testWidgets('says how much text landed once the upload succeeds',
        (tester) async {
      await pump(
        tester,
        const OcrRunBanner(),
        overrides: [
          ocrRunControllerProvider.overrideWith(
            () => _FixedRunController(
              const OcrRunState(phase: OcrRunPhase.done, wordCount: 812),
            ),
          ),
        ],
      );

      expect(
        find.text('Text extracted — 812 words are now searchable.'),
        findsOneWidget,
      );
    });
  });
}
