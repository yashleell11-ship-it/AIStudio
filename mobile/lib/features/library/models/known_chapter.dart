/// One entry in a followed series' known-chapter snapshot / live chapter
/// list (`backend/services/followed_series_service.py`).
class KnownChapter {
  const KnownChapter({
    required this.key,
    this.number,
    this.title,
    this.publishedAt,
    this.pageCount,
  });

  final String key;
  final double? number;
  final String? title;
  /// The source's RAW date string, unparsed. Sources publish wildly
  /// different shapes and several are not ISO at all, so parsing here threw
  /// the value away for those sources and the row rendered no date. See
  /// `chapterDateLabel`, which owns the parse and passes through what it
  /// cannot read.
  final String? publishedAt;

  /// Only present on the cache-backed detail chapter list.
  final int? pageCount;

  factory KnownChapter.fromJson(Map<String, dynamic> json) => KnownChapter(
        key: json['key'] as String,
        number: (json['number'] as num?)?.toDouble(),
        title: json['title'] as String?,
        publishedAt: json['published_at'] as String?,
        pageCount: (json['page_count'] as num?)?.toInt(),
      );

  /// Round-trips through [KnownChapter.fromJson] — the write half of the
  /// offline library cache, so a cached series lists the same chapters it
  /// listed online.
  Map<String, dynamic> toJson() => {
        'key': key,
        'number': number,
        'title': title,
        'published_at': publishedAt,
        'page_count': pageCount,
      };
}
