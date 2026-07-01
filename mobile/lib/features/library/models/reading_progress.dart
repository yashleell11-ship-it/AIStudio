class ReadingProgress {
  const ReadingProgress({
    required this.seriesId,
    required this.chapterId,
    required this.lastPage,
    required this.progressPct,
    required this.lastReadAt,
  });

  final int seriesId;
  final int chapterId;
  final int lastPage;
  final double progressPct;
  final DateTime lastReadAt;

  factory ReadingProgress.fromJson(Map<String, dynamic> json) => ReadingProgress(
        seriesId: json['series_id'] as int,
        chapterId: json['chapter_id'] as int,
        lastPage: json['last_page'] as int,
        progressPct: (json['progress_pct'] as num).toDouble(),
        lastReadAt: DateTime.parse(json['last_read_at'] as String),
      );

  Map<String, dynamic> toJson() => {
        'series_id': seriesId,
        'chapter_id': chapterId,
        'last_page': lastPage,
        'progress_pct': progressPct,
        'last_read_at': lastReadAt.toIso8601String(),
      };
}
