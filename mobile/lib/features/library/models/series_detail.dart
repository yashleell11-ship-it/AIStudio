import 'package:manhwamaniacs/features/library/models/chapter.dart';
import 'package:manhwamaniacs/features/library/models/collection.dart';
import 'package:manhwamaniacs/features/library/models/reading_progress.dart';
import 'package:manhwamaniacs/features/library/models/series_summary.dart';
import 'package:manhwamaniacs/features/library/models/tag.dart';

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
    this.sourceId,
    this.sourceSeriesId,
    this.isFollowed = false,
    this.followTrackerId,
  });

  final List<ChapterSummary> chapters;
  final List<Tag> tags;
  final List<CollectionRef> collections;

  /// Online source id this library series is linked to (e.g. 'asurascans'),
  /// or null when the series has no source linkage.
  final String? sourceId;

  /// The source's series id (e.g. 'killer-pietro-a80d257e'), or null.
  final String? sourceSeriesId;

  /// Whether the active (user, profile) follows this series for new-chapter
  /// notifications. Always false when [sourceId] is null: a hand-imported CBZ
  /// folder has no origin to check for updates. A "downloaded" tracker does
  /// not count -- the backend only reports `track_kind="followed"` here, so
  /// every downloaded series does not read as already-followed.
  final bool isFollowed;

  /// Id of the followed tracker behind [isFollowed], so Unfollow can DELETE it
  /// without a lookup round trip. Non-null iff [isFollowed] is true.
  final int? followTrackerId;

  /// True when this series can be followed at all — i.e. it resolves back to
  /// the source it was downloaded from. The two ids are always both set or
  /// both null, but both are checked so callers can use them non-null.
  bool get hasSourceLink => sourceId != null && sourceSeriesId != null;

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
      sourceId: sourceId,
      sourceSeriesId: sourceSeriesId,
      isFollowed: isFollowed,
      followTrackerId: followTrackerId,
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
      sourceId: json['source_id'] as String?,
      sourceSeriesId: json['source_series_id'] as String?,
      // The backend always sends `is_followed` as a real bool, but a null
      // guard keeps an older server (which omits it) rendering "Follow"
      // rather than crashing the whole series page on a cast.
      isFollowed: json['is_followed'] as bool? ?? false,
      followTrackerId: json['follow_tracker_id'] as int?,
    );
  }
}
