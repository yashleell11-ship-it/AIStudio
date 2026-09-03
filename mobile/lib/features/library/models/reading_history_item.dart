/// `GET /reader/history` row — a stored reading-position row
/// (`progress_service.py`'s `_serialize`, same shape as `ReadingProgress`).
/// Carries no series/chapter title.
class ReadingHistoryItem {
  const ReadingHistoryItem({
    required this.id,
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    this.chapterNumber,
    required this.lastPage,
    required this.pageCount,
    required this.isCompleted,
    this.lastReadAt,
  });

  final int id;
  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final double? chapterNumber;
  final int lastPage;
  final int pageCount;
  final bool isCompleted;
  final DateTime? lastReadAt;

  factory ReadingHistoryItem.fromJson(Map<String, dynamic> json) => ReadingHistoryItem(
        id: json['id'] as int,
        sourceId: json['source_id'] as String,
        seriesKey: json['series_key'] as String,
        chapterKey: json['chapter_key'] as String,
        chapterNumber: (json['chapter_number'] as num?)?.toDouble(),
        lastPage: (json['last_page'] as num?)?.toInt() ?? 1,
        pageCount: (json['page_count'] as num?)?.toInt() ?? 0,
        isCompleted: json['is_completed'] as bool? ?? false,
        lastReadAt: json['last_read_at'] != null
            ? DateTime.tryParse(json['last_read_at'] as String)
            : null,
      );
}
