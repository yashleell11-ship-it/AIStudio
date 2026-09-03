/// A saved reading position, source-native (`POST /reader/bookmark`,
/// `GET /reader/bookmarks`). Rows carry no series/chapter titles — only the
/// identity triple, matching `backend/services/progress_service.py`.
class Bookmark {
  const Bookmark({
    required this.id,
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    required this.page,
    this.note,
    this.createdAt,
  });

  final int id;
  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final int page;
  final String? note;
  final DateTime? createdAt;

  factory Bookmark.fromJson(Map<String, dynamic> json) => Bookmark(
        id: json['id'] as int,
        sourceId: json['source_id'] as String,
        seriesKey: json['series_key'] as String,
        chapterKey: json['chapter_key'] as String,
        page: json['page'] as int,
        note: json['note'] as String?,
        createdAt: json['created_at'] != null
            ? DateTime.tryParse(json['created_at'] as String)
            : null,
      );
}
