class ReadingHistoryItem {
  const ReadingHistoryItem({
    required this.sessionId,
    required this.seriesId,
    this.seriesTitle,
    required this.chapterId,
    this.chapterTitle,
    required this.startPage,
    required this.endPage,
    required this.pagesRead,
    this.startedAt,
    this.endedAt,
  });

  final int sessionId;
  final int seriesId;
  final String? seriesTitle;
  final int chapterId;
  final String? chapterTitle;
  final int startPage;
  final int endPage;
  final int pagesRead;
  final DateTime? startedAt;
  final DateTime? endedAt;

  factory ReadingHistoryItem.fromJson(Map<String, dynamic> json) => ReadingHistoryItem(
        sessionId: json['session_id'] as int,
        seriesId: json['series_id'] as int,
        seriesTitle: json['series_title'] as String?,
        chapterId: json['chapter_id'] as int,
        chapterTitle: json['chapter_title'] as String?,
        startPage: json['start_page'] as int,
        endPage: json['end_page'] as int,
        pagesRead: json['pages_read'] as int,
        startedAt: json['started_at'] != null
            ? DateTime.tryParse(json['started_at'] as String)
            : null,
        endedAt:
            json['ended_at'] != null ? DateTime.tryParse(json['ended_at'] as String) : null,
      );
}

class ReadingCalendarDay {
  const ReadingCalendarDay({
    required this.day,
    required this.sessions,
    required this.pagesRead,
    required this.hasActivity,
  });

  final String day;
  final int sessions;
  final int pagesRead;
  final bool hasActivity;

  factory ReadingCalendarDay.fromJson(Map<String, dynamic> json) => ReadingCalendarDay(
        day: json['day'] as String,
        sessions: json['sessions'] as int,
        pagesRead: json['pages_read'] as int,
        hasActivity: json['has_activity'] as bool,
      );
}
