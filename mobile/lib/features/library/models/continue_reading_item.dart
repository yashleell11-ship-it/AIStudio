/// `GET /library/continue-reading` item — progress-service shape. Carries no
/// series/chapter title; callers resolve those by matching
/// `(sourceId, seriesKey)` against the followed-series list they already
/// hold, or by rendering the chapter number alone.
class ContinueReadingItem {
  const ContinueReadingItem({
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    this.chapterNumber,
    required this.lastPage,
    required this.pageCount,
    this.lastReadAt,
  });

  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final double? chapterNumber;
  final int lastPage;
  final int pageCount;
  final DateTime? lastReadAt;

  double get progressPct => pageCount > 0 ? lastPage / pageCount : 0;

  factory ContinueReadingItem.fromJson(Map<String, dynamic> json) =>
      ContinueReadingItem(
        sourceId: json['source_id'] as String,
        seriesKey: json['series_key'] as String,
        chapterKey: json['chapter_key'] as String,
        chapterNumber: (json['chapter_number'] as num?)?.toDouble(),
        lastPage: (json['last_page'] as num?)?.toInt() ?? 1,
        pageCount: (json['page_count'] as num?)?.toInt() ?? 0,
        lastReadAt: json['last_read_at'] != null
            ? DateTime.tryParse(json['last_read_at'] as String)
            : null,
      );
}
