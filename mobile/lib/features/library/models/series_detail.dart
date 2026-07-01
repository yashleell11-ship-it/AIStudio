import 'package:aistudio_mobile/features/library/models/chapter.dart';
import 'package:aistudio_mobile/features/library/models/collection.dart';
import 'package:aistudio_mobile/features/library/models/reading_progress.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/features/library/models/tag.dart';

class SeriesDetail extends SeriesSummary {
  const SeriesDetail({
    required super.id,
    required super.libraryId,
    required super.title,
    required super.sortTitle,
    super.originalTitle,
    super.author,
    super.artist,
    super.description,
    super.status,
    required super.contentRating,
    required super.language,
    super.year,
    super.coverPath,
    required super.folderPath,
    required super.isFavorite,
    required super.readingStatus,
    required super.chapterCount,
    required super.readChapters,
    required super.pageCount,
    required super.totalChapters,
    required super.totalPages,
    super.firstChapterId,
    required super.createdAt,
    required super.updatedAt,
    super.readingProgress,
    required this.chapters,
    required this.tags,
    required this.collections,
  });

  final List<ChapterSummary> chapters;
  final List<Tag> tags;
  final List<CollectionRef> collections;

  @override
  SeriesDetail copyWith({bool? isFavorite, ReadingProgress? readingProgress}) {
    return SeriesDetail(
      id: id,
      libraryId: libraryId,
      title: title,
      sortTitle: sortTitle,
      originalTitle: originalTitle,
      author: author,
      artist: artist,
      description: description,
      status: status,
      contentRating: contentRating,
      language: language,
      year: year,
      coverPath: coverPath,
      folderPath: folderPath,
      isFavorite: isFavorite ?? this.isFavorite,
      readingStatus: readingStatus,
      chapterCount: chapterCount,
      readChapters: readChapters,
      pageCount: pageCount,
      totalChapters: totalChapters,
      totalPages: totalPages,
      firstChapterId: firstChapterId,
      createdAt: createdAt,
      updatedAt: updatedAt,
      readingProgress: readingProgress ?? this.readingProgress,
      chapters: chapters,
      tags: tags,
      collections: collections,
    );
  }

  factory SeriesDetail.fromJson(Map<String, dynamic> json) {
    final base = SeriesSummary.fromJson(json);
    return SeriesDetail(
      id: base.id,
      libraryId: base.libraryId,
      title: base.title,
      sortTitle: base.sortTitle,
      originalTitle: base.originalTitle,
      author: base.author,
      artist: base.artist,
      description: base.description,
      status: base.status,
      contentRating: base.contentRating,
      language: base.language,
      year: base.year,
      coverPath: base.coverPath,
      folderPath: base.folderPath,
      isFavorite: base.isFavorite,
      readingStatus: base.readingStatus,
      chapterCount: base.chapterCount,
      readChapters: base.readChapters,
      pageCount: base.pageCount,
      totalChapters: base.totalChapters,
      totalPages: base.totalPages,
      firstChapterId: base.firstChapterId,
      createdAt: base.createdAt,
      updatedAt: base.updatedAt,
      readingProgress: base.readingProgress,
      chapters: (json['chapters'] as List<dynamic>)
          .map((e) => ChapterSummary.fromJson(e as Map<String, dynamic>))
          .toList(),
      tags: (json['tags'] as List<dynamic>)
          .map((e) => Tag.fromJson(e as Map<String, dynamic>))
          .toList(),
      collections: (json['collections'] as List<dynamic>)
          .map((e) => CollectionRef.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}
