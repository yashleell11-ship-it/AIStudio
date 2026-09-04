import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode_controller.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/models/downloaded_series_group.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloaded_series_provider.dart';

import '../../support/test_overrides.dart';

SavedChapter _chapter({
  required int rowId,
  required int bytes,
  String seriesKey = 'solo-leveling',
  DownloadKind kind = DownloadKind.manga,
}) =>
    SavedChapter(
      rowId: rowId,
      scopeId: 'u1p1',
      sourceId: 'asura',
      seriesKey: seriesKey,
      chapterKey: '$rowId',
      chapterNumber: rowId.toDouble(),
      title: null,
      seriesTitle: seriesKey,
      pageCount: 20,
      bytes: bytes,
      state: DownloadChapterState.complete,
      pinned: false,
      readAt: null,
      createdAt: DateTime.utc(2026),
      retryCount: 0,
      error: null,
      kind: kind,
    );

DownloadedSeriesGroup _group(String seriesKey, List<SavedChapter> chapters) =>
    DownloadedSeriesGroup(
      sourceId: 'asura',
      seriesKey: seriesKey,
      seriesTitle: seriesKey,
      chapters: chapters,
    );

const _mangaOnly = ContentModeScope(
  mode: ContentMode.manga,
  index: {},
  novelsEnabled: true,
);

void main() {
  group('DownloadedSeriesGroup.totalBytes', () {
    test('is summed once and reused', () {
      final group = _group('a', [
        _chapter(rowId: 1, bytes: 100),
        _chapter(rowId: 2, bytes: 50),
      ]);

      expect(group.totalBytes, 150);
      expect(group.totalBytes, 150);
    });
  });

  group('groupsInMode', () {
    test('passes everything through with the novels gate shut', () {
      const scope = ContentModeScope(
        mode: ContentMode.manga,
        index: {},
        novelsEnabled: false,
      );
      final groups = [
        _group('a', [_chapter(rowId: 1, bytes: 1, kind: DownloadKind.novel)]),
      ];

      expect(identical(groupsInMode(groups, scope), groups), isTrue);
    });

    test('keeps only the rows of the active mode, dropping emptied series', () {
      final groups = [
        _group('mixed', [
          _chapter(rowId: 1, bytes: 10),
          _chapter(rowId: 2, bytes: 20, kind: DownloadKind.novel),
        ]),
        _group('prose', [
          _chapter(rowId: 3, bytes: 30, kind: DownloadKind.novel),
        ]),
      ];

      final kept = groupsInMode(groups, _mangaOnly);

      expect(kept.map((g) => g.seriesKey), ['mixed']);
      expect(kept.single.chapters.map((c) => c.rowId), [1]);
      // The filtered group carries its own size, not the unfiltered one.
      expect(kept.single.totalBytes, 10);
    });

    test('filters queue rows on their own kind, never the source index', () {
      final rows = [
        _chapter(rowId: 1, bytes: 10),
        _chapter(rowId: 2, bytes: 20, kind: DownloadKind.novel),
      ];

      expect(chaptersInMode(rows, _mangaOnly).map((c) => c.rowId), [1]);
    });
  });

  group('downloadedShelfProvider', () {
    test('orders the shelf largest series first', () async {
      final container = ProviderContainer(
        overrides: [
          ...contentModeOverrides(),
          downloadedSeriesProvider.overrideWith(
            (ref) async => [
              _group('small', [_chapter(rowId: 1, bytes: 100)]),
              _group('large', [
                _chapter(rowId: 2, bytes: 900),
                _chapter(rowId: 3, bytes: 100),
              ]),
              _group('middle', [_chapter(rowId: 4, bytes: 500)]),
            ],
          ),
        ],
      );
      addTearDown(container.dispose);
      final subscription =
          container.listen(downloadedShelfProvider, (_, __) {}, fireImmediately: true);

      await container.read(downloadedSeriesProvider.future);

      expect(
        subscription.read().requireValue.map((g) => g.seriesKey),
        ['large', 'middle', 'small'],
      );
    });

    test('does not reorder the list the source provider handed it', () async {
      final source = [
        _group('small', [_chapter(rowId: 1, bytes: 100)]),
        _group('large', [_chapter(rowId: 2, bytes: 900)]),
      ];
      final container = ProviderContainer(
        overrides: [
          ...contentModeOverrides(),
          downloadedSeriesProvider.overrideWith((ref) async => source),
        ],
      );
      addTearDown(container.dispose);
      final subscription =
          container.listen(downloadedShelfProvider, (_, __) {}, fireImmediately: true);

      await container.read(downloadedSeriesProvider.future);
      subscription.read();

      expect(source.map((g) => g.seriesKey), ['small', 'large']);
    });
  });
}
