import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode.dart';
import 'package:manhwamaniacs/features/sources/models/source.dart';

SourceSummary _source(String id, {String kind = 'manga'}) => SourceSummary(
      id: id,
      name: id,
      description: '',
      browsable: true,
      supportsImport: false,
      contentKind: kind,
    );

/// One row shape standing in for the half-dozen the app actually filters
/// (follows, notifications, history, bookmarks, downloads) — all of them carry
/// a source id and no kind, which is the whole reason the index exists.
typedef _Row = ({String? sourceId, String label});

void main() {
  final sources = [
    _source('asura'),
    _source('mangadex'),
    _source('royalroad', kind: 'novel'),
    _source('freewebnovel', kind: 'novel'),
    // A connector from before content_kind existed, or one that simply omits
    // it: the wire default, not a third mode.
    const SourceSummary(
      id: 'legacy',
      name: 'legacy',
      description: '',
      browsable: true,
      supportsImport: false,
    ),
  ];
  final index = buildSourceModeIndex(sources);

  group('invariant 1 — manga mode is today\'s app, exactly', () {
    test('the predicate is "not a novel", so an unlabelled source is manga',
        () {
      expect(sourceContentMode(_source('legacy')), ContentMode.manga);
      expect(index['legacy'], ContentMode.manga);
      expect(sourceContentMode(null), ContentMode.manga);
    });

    test('a source_id the listing does not carry stays where it shows today',
        () {
      // Connector removed, hidden by the 18+ gate, or /sources not back yet.
      expect(matchesContentMode('gone', index, ContentMode.manga), isTrue);
      expect(matchesContentMode('gone', index, ContentMode.novel), isFalse);
      expect(matchesContentMode(null, index, ContentMode.manga), isTrue);
    });

    test('an empty index — offline, cold start — blanks nothing', () {
      final rows = <_Row>[
        (sourceId: 'asura', label: 'a'),
        (sourceId: 'royalroad', label: 'b'),
      ];
      expect(
        filterByContentMode(
          rows,
          const {},
          ContentMode.manga,
          sourceIdOf: (r) => r.sourceId,
          novelsEnabled: true,
        ),
        hasLength(2),
      );
    });
  });

  group('invariant 2 — flag off means no mode at all', () {
    test('the effective mode is manga whatever is stored', () {
      expect(
        resolveContentMode(ContentMode.novel, novelsEnabled: false),
        ContentMode.manga,
      );
      expect(
        resolveContentMode(ContentMode.novel, novelsEnabled: true),
        ContentMode.novel,
      );
      expect(resolveContentMode(null, novelsEnabled: true), ContentMode.manga);
    });

    test('every filter is a pass-through, not a filter to manga', () {
      final rows = <_Row>[
        (sourceId: 'asura', label: 'a'),
        (sourceId: 'royalroad', label: 'b'),
        (sourceId: null, label: 'c'),
      ];
      // Identical output to no filtering at all — the filter cannot be the
      // thing that broke a list on a deployment that has no novels.
      expect(
        filterByContentMode(
          rows,
          index,
          ContentMode.manga,
          sourceIdOf: (r) => r.sourceId,
          novelsEnabled: false,
        ),
        same(rows),
      );
      expect(
        filterSourcesByContentMode(
          sources,
          ContentMode.manga,
          novelsEnabled: false,
        ),
        same(sources),
      );
    });

    test('OCR stays visible, because there is only one mode', () {
      expect(isOcrVisible(ContentMode.manga, novelsEnabled: false), isTrue);
      expect(isOcrVisible(ContentMode.novel, novelsEnabled: false), isTrue);
    });
  });

  group('scoping rows', () {
    final rows = <_Row>[
      (sourceId: 'asura', label: 'manhwa'),
      (sourceId: 'royalroad', label: 'novel'),
      (sourceId: 'legacy', label: 'unlabelled'),
      (sourceId: 'gone', label: 'orphan'),
      (sourceId: null, label: 'no source'),
    ];

    test('manga mode keeps everything that is not a novel', () {
      final kept = filterByContentMode(
        rows,
        index,
        ContentMode.manga,
        sourceIdOf: (r) => r.sourceId,
        novelsEnabled: true,
      ).map((r) => r.label);
      expect(kept, ['manhwa', 'unlabelled', 'orphan', 'no source']);
    });

    test('novel mode keeps only what the listing called a novel', () {
      final kept = filterByContentMode(
        rows,
        index,
        ContentMode.novel,
        sourceIdOf: (r) => r.sourceId,
        novelsEnabled: true,
      ).map((r) => r.label);
      expect(kept, ['novel']);
    });

    test('sources filter straight off content_kind, no index needed', () {
      expect(
        filterSourcesByContentMode(
          sources,
          ContentMode.novel,
          novelsEnabled: true,
        ).map((s) => s.id),
        ['royalroad', 'freewebnovel'],
      );
      expect(
        filterSourcesByContentMode(
          sources,
          ContentMode.manga,
          novelsEnabled: true,
        ).map((s) => s.id),
        ['asura', 'mangadex', 'legacy'],
      );
    });
  });

  group('OCR is manga-only', () {
    test('hidden in Novels mode — it searches text read off page images', () {
      expect(isOcrVisible(ContentMode.novel, novelsEnabled: true), isFalse);
      expect(isOcrVisible(ContentMode.manga, novelsEnabled: true), isTrue);
    });
  });

  group('persistence round-trip', () {
    test('parses what it writes and nothing else', () {
      for (final mode in ContentMode.values) {
        expect(ContentMode.parse(mode.wire), mode);
      }
      expect(ContentMode.parse('  novel  '), ContentMode.novel);
      expect(ContentMode.parse('manhwa'), isNull);
      expect(ContentMode.parse(''), isNull);
      expect(ContentMode.parse(null), isNull);
    });

    test('content_kind is read tolerantly off the wire', () {
      expect(
        SourceSummary.fromJson({
          'id': 'x',
          'name': 'X',
          'description': '',
          'browsable': true,
          'supports_import': false,
          'content_kind': 'novel',
        }).contentKind,
        kNovelContentKind,
      );
      // Absent, or the wrong type from a misbehaving server: manga.
      expect(
        SourceSummary.fromJson({
          'id': 'x',
          'name': 'X',
          'description': '',
          'browsable': true,
          'supports_import': false,
        }).contentKind,
        kMangaContentKind,
      );
      expect(
        SourceSummary.fromJson({
          'id': 'x',
          'name': 'X',
          'description': '',
          'browsable': true,
          'supports_import': false,
          'content_kind': 7,
        }).contentKind,
        kMangaContentKind,
      );
    });
  });
}
