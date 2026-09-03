import 'package:manhwamaniacs/core/network/api_image.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reader_page.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';

/// `GET /reader/chapter/manifest` — the download plan for a chapter: ordered
/// page list plus adjacent chapter keys. Mirrors the web's `ChapterManifest`
/// (`frontend/src/features/reader/api.ts`).
class ChapterManifest {
  const ChapterManifest({
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    required this.chapterNumber,
    required this.pageCount,
    required this.pages,
    required this.prev,
    required this.next,
  });

  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final double? chapterNumber;
  final int pageCount;
  final List<ManifestPage> pages;

  /// Adjacent chapter keys, or null at the ends.
  final String? prev;
  final String? next;

  factory ChapterManifest.fromJson(Map<String, dynamic> json) => ChapterManifest(
        sourceId: json['source_id'] as String,
        seriesKey: json['series_key'] as String,
        chapterKey: json['chapter_key'] as String,
        chapterNumber: (json['chapter_number'] as num?)?.toDouble(),
        pageCount: json['page_count'] as int,
        pages: (json['pages'] as List<dynamic>? ?? const [])
            .map((e) => ManifestPage.fromJson(e as Map<String, dynamic>))
            .toList(),
        prev: json['prev'] as String?,
        next: json['next'] as String?,
      );

  /// Build a [ReaderChapter] (the shape [ReaderContent] renders) from this
  /// manifest — the sole content builder for the manifest-driven reader.
  ReaderChapter toReaderChapter(String apiBaseUrl) {
    final title = chapterLabel(number: chapterNumber, title: null).primary;
    return ReaderChapter(
      id: chapterKey,
      seriesId: seriesKey,
      title: title,
      pageCount: pageCount,
      sourceId: sourceId,
      previousChapterId: prev,
      nextChapterId: next,
      pages: pages
          .map(
            (page) => ReaderPage(
              id: '$chapterKey:${page.number}',
              number: page.number,
              imageUrl: resolveApiResourceUrl(apiBaseUrl, page.url),
            ),
          )
          .toList(),
    );
  }
}

class ManifestPage {
  const ManifestPage({required this.number, required this.url});

  final int number;
  final String url;

  factory ManifestPage.fromJson(Map<String, dynamic> json) => ManifestPage(
        number: json['number'] as int,
        url: json['url'] as String,
      );
}
