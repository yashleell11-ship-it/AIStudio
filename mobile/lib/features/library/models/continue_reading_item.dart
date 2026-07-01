class ContinueReadingItem {
  const ContinueReadingItem({
    required this.seriesId,
    required this.seriesTitle,
    required this.chapterId,
    required this.chapterTitle,
    required this.lastPage,
    required this.progressPct,
    required this.lastReadAt,
    this.coverPath,
  });

  final int seriesId;
  final String seriesTitle;
  final int chapterId;
  final String chapterTitle;
  final int lastPage;
  final double progressPct;
  final DateTime lastReadAt;
  final String? coverPath;

  factory ContinueReadingItem.fromJson(Map<String, dynamic> json) =>
      ContinueReadingItem(
        seriesId: json['series_id'] as int,
        seriesTitle: json['series_title'] as String,
        chapterId: json['chapter_id'] as int,
        chapterTitle: json['chapter_title'] as String,
        lastPage: json['last_page'] as int,
        progressPct: (json['progress_pct'] as num).toDouble(),
        lastReadAt: DateTime.parse(json['last_read_at'] as String),
        coverPath: json['cover_path'] as String?,
      );
}
