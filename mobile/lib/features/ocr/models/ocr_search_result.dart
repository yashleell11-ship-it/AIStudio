import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';

/// One `GET /ocr/search` hit — a chapter whose OCR text matched, plus the
/// server-built snippet around the match.
class OcrSearchResult {
  const OcrSearchResult({
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    required this.snippet,
    required this.wordCount,
    required this.engine,
    required this.highlightedTerms,
  });

  final String sourceId;
  final String seriesKey;
  final String chapterKey;

  /// Contains `<mark>…</mark>` around each matched term — the backend builds
  /// it for the web client, which renders HTML. See `ocrSnippetSpans` for
  /// the Flutter-side reader of it.
  final String snippet;
  final int wordCount;
  final String? engine;
  final List<String> highlightedTerms;

  ChapterIdentity get identity =>
      (sourceId: sourceId, seriesKey: seriesKey, chapterKey: chapterKey);

  factory OcrSearchResult.fromJson(Map<String, dynamic> json) => OcrSearchResult(
        sourceId: json['source_id'] as String? ?? '',
        seriesKey: json['series_key'] as String? ?? '',
        chapterKey: json['chapter_key'] as String? ?? '',
        snippet: json['snippet'] as String? ?? '',
        wordCount: (json['word_count'] as num?)?.toInt() ?? 0,
        engine: json['engine'] as String?,
        highlightedTerms: [
          if (json['highlighted_terms'] case final List<dynamic> terms)
            for (final term in terms)
              if (term is String) term,
        ],
      );
}

/// One page of search results. `total` counts every match the caller is
/// allowed to see (the backend filters to followed series + the 18+ gate
/// *before* paginating), so it is a real total, not an estimate.
class OcrSearchPage {
  const OcrSearchPage({
    required this.items,
    required this.total,
    required this.offset,
    required this.limit,
    required this.hasMore,
  });

  final List<OcrSearchResult> items;
  final int total;
  final int offset;
  final int limit;
  final bool hasMore;

  static const OcrSearchPage empty = OcrSearchPage(
    items: [],
    total: 0,
    offset: 0,
    limit: 0,
    hasMore: false,
  );

  factory OcrSearchPage.fromJson(Map<String, dynamic> json) {
    final items = json['items'];
    final offset = (json['offset'] as num?)?.toInt() ?? 0;
    final limit = (json['limit'] as num?)?.toInt() ?? 0;
    final total = (json['total'] as num?)?.toInt() ?? 0;
    return OcrSearchPage(
      items: [
        if (items is List)
          for (final item in items)
            if (item is Map<String, dynamic>) OcrSearchResult.fromJson(item),
      ],
      total: total,
      offset: offset,
      limit: limit,
      // `has_more` is computed server-side but only on the non-empty path;
      // deriving it here as a fallback keeps an empty-query response (which
      // omits it) from reading as "there is another page".
      hasMore: json['has_more'] as bool? ?? offset + limit < total,
    );
  }
}
