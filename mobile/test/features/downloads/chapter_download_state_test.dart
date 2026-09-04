import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/providers/series_download_status_provider.dart';
import 'package:manhwamaniacs/features/downloads/widgets/chapter_download_action.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_chapter_tile.dart';

/// The bug this file pins: `queued`, `downloading` and `complete` all used to
/// build the *same* disabled icon button, so a chapter being fetched, one
/// waiting its turn and one entirely on the phone were indistinguishable on a
/// series page — and a page counter had nowhere to render at all.
SeriesChapterDownloadAction? _actionFor(
  DownloadChapterState? state, {
  bool hasScope = true,
  String? error,
  ChapterDownloadProgress? progress,
}) =>
    chapterDownloadAction(
      hasScope: hasScope,
      status: state == null ? null : (state: state, error: error),
      onDownload: () {},
      progress: progress,
      buttonKey: const Key('download-ch-1'),
    );

Widget _tileHost(SeriesChapterDownloadAction? download) => MaterialApp(
      home: Scaffold(
        body: SeriesChapterTile(
          label: const ChapterLabel(primary: 'Chapter 1'),
          download: download,
        ),
      ),
    );

void main() {
  group('chapterDownloadAction gives every store state its own phase', () {
    test('a chapter with no row at all offers to download', () {
      final action = _actionFor(null)!;
      expect(action.phase, SeriesChapterDownloadPhase.notDownloaded);
      expect(action.onPressed, isNotNull);
      expect(action.statusText, isNull);
    });

    test('queued says so, and is not pressable', () {
      final action = _actionFor(DownloadChapterState.queued)!;
      expect(action.phase, SeriesChapterDownloadPhase.queued);
      expect(action.statusText, 'Queued for download');
      expect(action.onPressed, isNull);
    });

    test('downloading carries the live page counter', () {
      final action = _actionFor(
        DownloadChapterState.downloading,
        progress: (pagesDone: 8, pageTotal: 20),
      )!;
      expect(action.phase, SeriesChapterDownloadPhase.downloading);
      expect(action.statusText, 'Downloading · page 8 of 20');
      expect(action.progressValue, closeTo(0.4, 0.0001));
    });

    test(
      'downloading before the manifest lands stays indeterminate rather than '
      'claiming "page 0 of 0"',
      () {
        final action = _actionFor(
          DownloadChapterState.downloading,
          progress: (pagesDone: 0, pageTotal: 0),
        )!;
        expect(action.progressValue, isNull);
        expect(action.statusText, contains('reading chapter details'));
      },
    );

    test('a complete chapter is marked saved, not merely un-pressable', () {
      final action = _actionFor(DownloadChapterState.complete)!;
      expect(action.phase, SeriesChapterDownloadPhase.downloaded);
      expect(action.statusText, 'Saved offline');
    });

    test('failed offers a retry and names the failure', () {
      final action =
          _actionFor(DownloadChapterState.failed, error: 'page 4 timed out')!;
      expect(action.phase, SeriesChapterDownloadPhase.failed);
      expect(action.onPressed, isNotNull);
      expect(action.statusText, 'Download failed — page 4 timed out');
    });

    test('no active (user, profile) scope means no control at all', () {
      expect(_actionFor(null, hasScope: false), isNull);
      expect(_actionFor(DownloadChapterState.complete, hasScope: false), isNull);
    });

    test('the five states never collapse onto one phase', () {
      final phases = {
        _actionFor(null)!.phase,
        _actionFor(DownloadChapterState.queued)!.phase,
        _actionFor(DownloadChapterState.downloading)!.phase,
        _actionFor(DownloadChapterState.complete)!.phase,
        _actionFor(DownloadChapterState.failed)!.phase,
      };
      expect(phases, hasLength(5));
    });
  });

  group('a chapter row renders each phase differently', () {
    testWidgets('not downloaded: a pressable download button', (tester) async {
      await tester.pumpWidget(_tileHost(_actionFor(null)));

      final button = tester.widget<IconButton>(
        find.byKey(const Key('download-ch-1')),
      );
      expect(button.onPressed, isNotNull);
      expect((button.icon as Icon).icon, Icons.download_outlined);
    });

    testWidgets('queued: a waiting badge and the words to match', (tester) async {
      await tester.pumpWidget(
        _tileHost(_actionFor(DownloadChapterState.queued)),
      );

      expect(find.byIcon(Icons.schedule), findsOneWidget);
      expect(find.text('Queued for download'), findsOneWidget);
      // Not a button any more: nothing here for the user to press.
      expect(find.byType(IconButton), findsNothing);
    });

    testWidgets('downloading: a determinate bar and "page 8 of 20"',
        (tester) async {
      await tester.pumpWidget(
        _tileHost(
          _actionFor(
            DownloadChapterState.downloading,
            progress: (pagesDone: 8, pageTotal: 20),
          ),
        ),
      );

      expect(find.text('Downloading · page 8 of 20'), findsOneWidget);
      final bar = tester.widget<LinearProgressIndicator>(
        find.byKey(const Key('chapter-download-bar')),
      );
      expect(bar.value, closeTo(0.4, 0.0001));
    });

    testWidgets('downloaded: an unmistakable persistent marker', (tester) async {
      await tester.pumpWidget(
        _tileHost(_actionFor(DownloadChapterState.complete)),
      );

      expect(find.byIcon(Icons.offline_pin), findsOneWidget);
      expect(find.text('Saved offline'), findsOneWidget);
      expect(find.byIcon(Icons.download_outlined), findsNothing);
    });

    testWidgets('failed: a retry button, in the danger colour', (tester) async {
      await tester.pumpWidget(
        _tileHost(_actionFor(DownloadChapterState.failed, error: 'HTTP 503')),
      );

      final button = tester.widget<IconButton>(
        find.byKey(const Key('download-ch-1')),
      );
      expect(button.onPressed, isNotNull);
      expect((button.icon as Icon).icon, Icons.refresh);
      expect(find.text('Download failed — HTTP 503'), findsOneWidget);
    });

    testWidgets(
      'the three states that used to look identical no longer do',
      (tester) async {
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ListView(
                children: [
                  for (final state in [
                    DownloadChapterState.queued,
                    DownloadChapterState.downloading,
                    DownloadChapterState.complete,
                  ])
                    SeriesChapterTile(
                      label: ChapterLabel(primary: 'Chapter ${state.name}'),
                      download: _actionFor(
                        state,
                        progress: (pagesDone: 3, pageTotal: 10),
                      ),
                    ),
                ],
              ),
            ),
          ),
        );

        expect(find.text('Queued for download'), findsOneWidget);
        expect(find.text('Downloading · page 3 of 10'), findsOneWidget);
        expect(find.text('Saved offline'), findsOneWidget);
        expect(find.byIcon(Icons.schedule), findsOneWidget);
        expect(find.byIcon(Icons.offline_pin), findsOneWidget);
      },
    );
  });
}
