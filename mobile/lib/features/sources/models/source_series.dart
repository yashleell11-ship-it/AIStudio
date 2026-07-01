class SourceSeriesSummary {
  const SourceSeriesSummary({
    required this.id,
    required this.sourceId,
    required this.title,
    required this.chapterCount,
    this.description,
    this.author,
    this.artist,
    this.status,
    required this.genres,
    this.latestChapter,
    required this.coverUrl,
  });

  final String id;
  final String sourceId;
  final String title;
  final int chapterCount;
  final String? description;
  final String? author;
  final String? artist;
  final String? status;
  final List<String> genres;
  final String? latestChapter;
  final String coverUrl;

  factory SourceSeriesSummary.fromJson(Map<String, dynamic> json, String apiBaseUrl) {
    final rawCover = json['cover_url'] as String;
    final coverUrl =
        rawCover.startsWith('http') ? rawCover : '$apiBaseUrl$rawCover';
    return SourceSeriesSummary(
      id: json['id'] as String,
      sourceId: json['source_id'] as String,
      title: json['title'] as String,
      chapterCount: json['chapter_count'] as int,
      description: json['description'] as String?,
      author: json['author'] as String?,
      artist: json['artist'] as String?,
      status: json['status'] as String?,
      genres: (json['genres'] as List<dynamic>).cast<String>(),
      latestChapter: json['latest_chapter'] as String?,
      coverUrl: coverUrl,
    );
  }
}

class SourceChapterSummary {
  const SourceChapterSummary({
    required this.id,
    required this.sourceId,
    required this.seriesId,
    required this.title,
    this.number,
    required this.pageCount,
    this.releaseDate,
  });

  final String id;
  final String sourceId;
  final String seriesId;
  final String title;
  final double? number;
  final int pageCount;
  final DateTime? releaseDate;

  factory SourceChapterSummary.fromJson(Map<String, dynamic> json) => SourceChapterSummary(
        id: json['id'] as String,
        sourceId: json['source_id'] as String,
        seriesId: json['series_id'] as String,
        title: json['title'] as String,
        number: json['number'] != null ? (json['number'] as num).toDouble() : null,
        pageCount: json['page_count'] as int,
        releaseDate: json['release_date'] != null
            ? DateTime.tryParse(json['release_date'] as String)
            : null,
      );
}
