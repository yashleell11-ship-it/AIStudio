class UpdateNotification {
  const UpdateNotification({
    required this.id,
    required this.trackerId,
    required this.source,
    required this.seriesId,
    required this.seriesTitle,
    required this.chapterId,
    required this.chapterTitle,
    this.chapterNumber,
    required this.isRead,
    this.createdAt,
  });

  final int id;
  final int trackerId;
  final String source;
  final String seriesId;
  final String seriesTitle;
  final String chapterId;
  final String chapterTitle;
  final double? chapterNumber;
  final bool isRead;
  final DateTime? createdAt;

  factory UpdateNotification.fromJson(Map<String, dynamic> json) =>
      UpdateNotification(
        id: json['id'] as int,
        trackerId: json['tracker_id'] as int,
        source: json['source'] as String,
        seriesId: json['series_id'] as String,
        seriesTitle: json['series_title'] as String,
        chapterId: json['chapter_id'] as String,
        chapterTitle: json['chapter_title'] as String,
        chapterNumber: json['chapter_number'] != null
            ? (json['chapter_number'] as num).toDouble()
            : null,
        isRead: json['is_read'] as bool,
        createdAt: json['created_at'] != null
            ? DateTime.tryParse(json['created_at'] as String)
            : null,
      );
}
