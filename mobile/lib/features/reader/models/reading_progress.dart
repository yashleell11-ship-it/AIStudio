/// Source-native reading position, as stored/returned by
/// `POST /reader/progress`, `POST /reader/progress/batch` and
/// `GET /reader/progress/series` (`backend/services/progress_service.py`).
class ReadingProgress {
  const ReadingProgress({
    required this.id,
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    required this.chapterNumber,
    required this.lastPage,
    required this.pageCount,
    required this.scrollOffsetPx,
    required this.isCompleted,
    this.startedAt,
    this.lastReadAt,
    this.completedAt,
    required this.timeSpentSeconds,
    this.advanced,
  });

  final int id;
  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final double? chapterNumber;
  final int lastPage;
  final int pageCount;
  final int scrollOffsetPx;
  final bool isCompleted;
  final DateTime? startedAt;
  final DateTime? lastReadAt;
  final DateTime? completedAt;
  final int timeSpentSeconds;

  /// Only present on the `POST /reader/progress` response: did the stored row
  /// advance?
  final bool? advanced;

  factory ReadingProgress.fromJson(Map<String, dynamic> json) => ReadingProgress(
        id: json['id'] as int,
        sourceId: json['source_id'] as String,
        seriesKey: json['series_key'] as String,
        chapterKey: json['chapter_key'] as String,
        chapterNumber: (json['chapter_number'] as num?)?.toDouble(),
        lastPage: json['last_page'] as int,
        pageCount: json['page_count'] as int,
        scrollOffsetPx: json['scroll_offset_px'] as int,
        isCompleted: json['is_completed'] as bool,
        startedAt: json['started_at'] != null
            ? DateTime.tryParse(json['started_at'] as String)
            : null,
        lastReadAt: json['last_read_at'] != null
            ? DateTime.tryParse(json['last_read_at'] as String)
            : null,
        completedAt: json['completed_at'] != null
            ? DateTime.tryParse(json['completed_at'] as String)
            : null,
        timeSpentSeconds: json['time_spent_seconds'] as int,
        advanced: json['advanced'] as bool?,
      );
}

/// Push body for `POST /reader/progress` and `POST /reader/progress/batch`.
class ProgressPush {
  const ProgressPush({
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    this.chapterNumber,
    required this.lastPage,
    this.pageCount = 0,
    this.scrollOffsetPx = 0,
    this.isCompleted = false,
    this.timeSpentSeconds = 0,
  });

  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final double? chapterNumber;
  final int lastPage;
  final int pageCount;
  final int scrollOffsetPx;
  final bool isCompleted;
  final int timeSpentSeconds;

  Map<String, dynamic> toJson() => {
        'source_id': sourceId,
        'series_key': seriesKey,
        'chapter_key': chapterKey,
        if (chapterNumber != null) 'chapter_number': chapterNumber,
        'last_page': lastPage,
        'page_count': pageCount,
        'scroll_offset_px': scrollOffsetPx,
        'is_completed': isCompleted,
        'time_spent_seconds': timeSpentSeconds,
      };
}
