import 'package:flutter/foundation.dart';
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

  /// Value equality, because every screen that holds a chapter gets a **new**
  /// instance each time the provider behind it runs — `resolvedReaderChapter`
  /// rebuilds one from the manifest or from disk on every resolution, however
  /// unchanged the content. Comparing by reference therefore answers "did this
  /// re-resolve?" when the only question worth asking is "did it change?", and
  /// a reader that acts on the first answer tears down work it could have
  /// kept.
  ///
  /// Lives on the type rather than at the call site so the two readers — the
  /// manifest one and the source-browsing one — cannot drift into two
  /// different ideas of when a chapter is the same chapter.
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ReaderChapter &&
          other.id == id &&
          other.seriesId == seriesId &&
          other.title == title &&
          other.pageCount == pageCount &&
          other.sourceId == sourceId &&
          other.seriesTitle == seriesTitle &&
          other.previousChapterId == previousChapterId &&
          other.nextChapterId == nextChapterId &&
          listEquals(other.pages, pages);

  @override
  int get hashCode => Object.hash(
        id,
        seriesId,
        title,
        pageCount,
        sourceId,
        seriesTitle,
        previousChapterId,
        nextChapterId,
        Object.hashAll(pages),
      );

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
