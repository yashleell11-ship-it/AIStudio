import 'package:manhwamaniacs/features/novels/utils/novel_book.dart';
import 'package:manhwamaniacs/features/novels/utils/novel_progress.dart';

/// One chapter of prose, ready to render.
///
/// Built from `GET /novels/chapter?source=&series=&chapter=` — the novel
/// analog of the reader manifest.
///
/// [paragraphs] is SANITIZED PLAIN TEXT, never HTML: the connector strips
/// scripts, styles, ads and aggregator watermark lines before anything is
/// cached, so what arrives here is the canonical storage form. Rendering it as
/// text is therefore both the safe choice and the accurate one — and it is
/// what makes the offline copy a few kilobytes of JSON instead of a page
/// archive.
class NovelChapter {
  const NovelChapter({
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    required this.chapterNumber,
    required this.title,
    required this.paragraphs,
    required this.previousChapterKey,
    required this.nextChapterKey,
    required this.wordCount,
    this.isOffline = false,
  });

  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final double? chapterNumber;
  final String title;
  final List<String> paragraphs;

  /// Adjacent chapter keys, or null at the ends of the series — and always
  /// null when [isOffline], since the store knows a chapter's bytes but not
  /// its neighbours.
  final String? previousChapterKey;
  final String? nextChapterKey;
  final int wordCount;

  /// True when this was reconstructed from the on-device store with no
  /// network call at all.
  final bool isOffline;

  /// How many progress buckets this chapter's paragraphs map onto — what goes
  /// in `page_count` (see `utils/novel_progress.dart`).
  int get buckets => bucketCount(paragraphs.length);

  /// The title falls back to the chapter number and then to a bare "Chapter":
  /// novel aggregators routinely publish untitled chapters, and a blank
  /// heading in the middle of a continuous scroll is worse than a generic one.
  static String resolveTitle(String? rawTitle, double? chapterNumber) {
    final trimmed = rawTitle?.trim();
    if (trimmed != null && trimmed.isNotEmpty) return trimmed;
    if (chapterNumber != null) {
      return 'Chapter ${formatChapterNumber(chapterNumber)}';
    }
    return 'Chapter';
  }

  factory NovelChapter.fromJson(Map<String, dynamic> json) {
    final paragraphs = <String>[
      for (final p in (json['paragraphs'] as List<dynamic>? ?? const []))
        if (p is String) p,
    ];
    final chapterNumber = (json['chapter_number'] as num?)?.toDouble();
    final reported = (json['word_count'] as num?)?.toInt() ?? 0;
    return NovelChapter(
      sourceId: json['source_id'] as String? ?? '',
      seriesKey: json['series_key'] as String? ?? '',
      chapterKey: json['chapter_key'] as String? ?? '',
      chapterNumber: chapterNumber,
      title: NovelChapter.resolveTitle(json['title'] as String?, chapterNumber),
      paragraphs: paragraphs,
      previousChapterKey: json['prev'] as String?,
      nextChapterKey: json['next'] as String?,
      // Trusted when the server sent one, recomputed from the paragraphs when
      // it did not (an older cache row, a payload shape that changed) — the
      // reading-time estimate is the main thing a reader looks at before
      // opening a chapter, so "unknown" is worth a cheap local count.
      wordCount: reported > 0 ? reported : countWords(paragraphs),
    );
  }

  /// The blob written to the on-device store, and read back by the offline
  /// path. Deliberately a narrow subset of the payload: the identity triple is
  /// already the store's key, and `prev`/`next` are network facts that go
  /// stale, so persisting them would let an offline reader offer a link it
  /// cannot follow.
  Map<String, dynamic> toStoredJson() => {
        'title': title,
        'chapter_number': chapterNumber,
        'paragraphs': paragraphs,
        'word_count': wordCount,
      };

  /// Rebuild from [toStoredJson] plus the identity the store holds separately.
  factory NovelChapter.fromStoredJson(
    Map<String, dynamic> json, {
    required String sourceId,
    required String seriesKey,
    required String chapterKey,
  }) {
    final paragraphs = <String>[
      for (final p in (json['paragraphs'] as List<dynamic>? ?? const []))
        if (p is String) p,
    ];
    final chapterNumber = (json['chapter_number'] as num?)?.toDouble();
    final reported = (json['word_count'] as num?)?.toInt() ?? 0;
    return NovelChapter(
      sourceId: sourceId,
      seriesKey: seriesKey,
      chapterKey: chapterKey,
      chapterNumber: chapterNumber,
      title: NovelChapter.resolveTitle(json['title'] as String?, chapterNumber),
      paragraphs: paragraphs,
      previousChapterKey: null,
      nextChapterKey: null,
      wordCount: reported > 0 ? reported : countWords(paragraphs),
      isOffline: true,
    );
  }
}
