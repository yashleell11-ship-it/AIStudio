import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/models/known_chapter.dart';

/// `GET /library/series/{followed_id}` — the follow row plus cache meta, the
/// live chapter list, and a `chapter_key -> progress` overlay.
class SeriesDetail extends FollowedSeries {
  const SeriesDetail({
    required super.id,
    required super.sourceId,
    required super.seriesKey,
    required super.title,
    required super.coverUrl,
    required super.isFavorite,
    required super.readingStatus,
    required super.notify,
    required super.sortOrder,
    required super.contentRating,
    required super.rating,
    super.matureOverride,
    super.knownChapters,
    required super.chapterCount,
    super.lastCheckedAt,
    super.createdAt,
    super.updatedAt,
    this.description,
    this.author,
    this.genres,
    required this.chapters,
    required this.progress,
  });

  final String? description;
  final String? author;
  final List<String>? genres;

  /// Live chapter list from the source cache (richer than [knownChapters]).
  final List<KnownChapter> chapters;

  /// `chapter_key -> progress` overlay for this profile.
  final Map<String, ChapterProgressEntry> progress;

  factory SeriesDetail.fromJson(Map<String, dynamic> json) {
    final base = FollowedSeries.fromJson(json);
    final progressJson = json['progress'] as Map<String, dynamic>? ?? const {};
    return SeriesDetail(
      id: base.id,
      sourceId: base.sourceId,
      seriesKey: base.seriesKey,
      title: base.title,
      coverUrl: base.coverUrl,
      isFavorite: base.isFavorite,
      readingStatus: base.readingStatus,
      notify: base.notify,
      sortOrder: base.sortOrder,
      contentRating: base.contentRating,
      rating: base.rating,
      matureOverride: base.matureOverride,
      knownChapters: base.knownChapters,
      chapterCount: base.chapterCount,
      lastCheckedAt: base.lastCheckedAt,
      createdAt: base.createdAt,
      updatedAt: base.updatedAt,
      description: json['description'] as String?,
      author: json['author'] as String?,
      genres: (json['genres'] as List<dynamic>?)?.cast<String>(),
      chapters: (json['chapters'] as List<dynamic>? ?? const [])
          .map((e) => KnownChapter.fromJson(e as Map<String, dynamic>))
          .toList(),
      progress: {
        for (final entry in progressJson.entries)
          entry.key:
              ChapterProgressEntry.fromJson(entry.value as Map<String, dynamic>),
      },
    );
  }
}
