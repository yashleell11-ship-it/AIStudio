class Bookmark {
  const Bookmark({
    required this.id,
    required this.seriesId,
    this.seriesTitle,
    required this.chapterId,
    this.chapterTitle,
    required this.page,
    this.note,
    required this.createdAt,
  });

  final int id;
  final int seriesId;
  final String? seriesTitle;
  final int chapterId;
  final String? chapterTitle;
  final int page;
  final String? note;
  final DateTime createdAt;

  factory Bookmark.fromJson(Map<String, dynamic> json) => Bookmark(
        id: json['id'] as int,
        seriesId: json['series_id'] as int,
        seriesTitle: json['series_title'] as String?,
        chapterId: json['chapter_id'] as int,
        chapterTitle: json['chapter_title'] as String?,
        page: json['page'] as int,
        note: json['note'] as String?,
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'series_id': seriesId,
        'series_title': seriesTitle,
        'chapter_id': chapterId,
        'chapter_title': chapterTitle,
        'page': page,
        'note': note,
        'created_at': createdAt.toIso8601String(),
      };
}
