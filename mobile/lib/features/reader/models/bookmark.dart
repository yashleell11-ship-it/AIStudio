class Bookmark {
  const Bookmark({
    required this.id,
    required this.seriesId,
    required this.chapterId,
    required this.page,
    this.note,
    required this.createdAt,
  });

  final int id;
  final int seriesId;
  final int chapterId;
  final int page;
  final String? note;
  final DateTime createdAt;

  factory Bookmark.fromJson(Map<String, dynamic> json) => Bookmark(
        id: json['id'] as int,
        seriesId: json['series_id'] as int,
        chapterId: json['chapter_id'] as int,
        page: json['page'] as int,
        note: json['note'] as String?,
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'series_id': seriesId,
        'chapter_id': chapterId,
        'page': page,
        'note': note,
        'created_at': createdAt.toIso8601String(),
      };
}
