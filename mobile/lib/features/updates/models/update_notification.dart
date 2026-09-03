/// One new-chapter notification
/// (`backend/services/update_service.py`'s `serialize_notification`).
class UpdateNotification {
  const UpdateNotification({
    required this.id,
    required this.followedSeriesId,
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    required this.chapterTitle,
    this.chapterNumber,
    required this.isRead,
    this.createdAt,
  });

  final int id;
  final int? followedSeriesId;
  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final String chapterTitle;
  final double? chapterNumber;
  final bool isRead;
  final DateTime? createdAt;

  factory UpdateNotification.fromJson(Map<String, dynamic> json) =>
      UpdateNotification(
        id: json['id'] as int,
        followedSeriesId: json['followed_series_id'] as int?,
        sourceId: json['source_id'] as String,
        seriesKey: json['series_key'] as String,
        chapterKey: json['chapter_key'] as String,
        chapterTitle: json['chapter_title'] as String,
        chapterNumber: (json['chapter_number'] as num?)?.toDouble(),
        isRead: json['is_read'] as bool,
        createdAt: json['created_at'] != null
            ? DateTime.tryParse(json['created_at'] as String)
            : null,
      );
}
