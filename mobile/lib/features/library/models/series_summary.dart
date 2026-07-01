import 'package:aistudio_mobile/features/library/models/reading_progress.dart';

class SeriesSummary {
  const SeriesSummary({
    required this.id,
    required this.libraryId,
    required this.title,
    required this.sortTitle,
    this.originalTitle,
    this.author,
    this.artist,
    this.description,
    this.status,
    required this.contentRating,
    required this.language,
    this.year,
    this.coverPath,
    required this.folderPath,
    required this.isFavorite,
    required this.readingStatus,
    required this.chapterCount,
    required this.readChapters,
    required this.pageCount,
    required this.totalChapters,
    required this.totalPages,
    this.firstChapterId,
    required this.createdAt,
    required this.updatedAt,
    this.readingProgress,
  });

  final int id;
  final int libraryId;
  final String title;
  final String sortTitle;
  final String? originalTitle;
  final String? author;
  final String? artist;
  final String? description;
  final String? status;
  final String contentRating;
  final String language;
  final int? year;
  final String? coverPath;
  final String folderPath;
  final bool isFavorite;
  final String readingStatus;
  final int chapterCount;
  final int readChapters;
  final int pageCount;
  final int totalChapters;
  final int totalPages;
  final int? firstChapterId;
  final DateTime createdAt;
  final DateTime updatedAt;
  final ReadingProgress? readingProgress;

  double get readProgressPct =>
      totalChapters > 0 ? readChapters / totalChapters : 0;

  factory SeriesSummary.fromJson(Map<String, dynamic> json) => SeriesSummary(
        id: json['id'] as int,
        libraryId: json['library_id'] as int,
        title: json['title'] as String,
        sortTitle: json['sort_title'] as String,
        originalTitle: json['original_title'] as String?,
        author: json['author'] as String?,
        artist: json['artist'] as String?,
        description: json['description'] as String?,
        status: json['status'] as String?,
        contentRating: json['content_rating'] as String,
        language: json['language'] as String,
        year: json['year'] as int?,
        coverPath: json['cover_path'] as String?,
        folderPath: json['folder_path'] as String,
        isFavorite: json['is_favorite'] as bool,
        readingStatus: json['reading_status'] as String,
        chapterCount: json['chapter_count'] as int,
        readChapters: json['read_chapters'] as int,
        pageCount: json['page_count'] as int,
        totalChapters: json['total_chapters'] as int,
        totalPages: json['total_pages'] as int,
        firstChapterId: json['first_chapter_id'] as int?,
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
        readingProgress: json['reading_progress'] != null
            ? ReadingProgress.fromJson(
                json['reading_progress'] as Map<String, dynamic>,
              )
            : null,
      );
}
