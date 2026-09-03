import 'package:manhwamaniacs/features/reader/models/reader_page.dart';

/// A renderable chapter for [ReaderContent] — either the source-browsing
/// payload (`GET /sources/{source}/series/{series}/chapters/{chapter}/reader`)
/// or a [ChapterManifest] mapped onto this shape via
/// [ChapterManifest.toReaderChapter].
class ReaderChapter {
  const ReaderChapter({
    required this.id,
    required this.seriesId,
    required this.title,
    required this.pageCount,
    required this.pages,
    this.sourceId,
    this.seriesTitle,
    this.previousChapterId,
    this.nextChapterId,
  });

  final String id;
  final String seriesId;
  final String title;
  final int pageCount;
  final List<ReaderPage> pages;
  final String? sourceId;
  final String? seriesTitle;
  final String? previousChapterId;
  final String? nextChapterId;

  factory ReaderChapter.fromJson(Map<String, dynamic> json, String apiBaseUrl) =>
      ReaderChapter(
        id: json['id'].toString(),
        seriesId: json['series_id'].toString(),
        title: json['title'] as String,
        pageCount: json['page_count'] as int,
        sourceId: json['source_id'] as String?,
        seriesTitle: json['series_title'] as String?,
        previousChapterId: json['previous_chapter_id']?.toString(),
        nextChapterId: json['next_chapter_id']?.toString(),
        pages: (json['pages'] as List<dynamic>)
            .map(
              (e) => ReaderPage.fromJson(
                e as Map<String, dynamic>,
                apiBaseUrl,
              ),
            )
            .toList(),
      );
}
