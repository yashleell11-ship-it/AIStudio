import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:aistudio_mobile/features/downloads/repositories/downloads_repository.dart';
import 'package:aistudio_mobile/features/library/models/chapter.dart';
import 'package:aistudio_mobile/features/library/repositories/library_repository.dart';
import 'package:aistudio_mobile/features/reader/models/reader_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/reader_page.dart';
import 'package:aistudio_mobile/features/reader/utils/page_image_url.dart';
import 'package:aistudio_mobile/features/sources/providers/source_reader_provider.dart';

/// Resolved local library ids for a downloaded source chapter.
class SourceReaderOfflineHandoff {
  const SourceReaderOfflineHandoff({
    required this.seriesId,
    required this.chapterId,
  });

  final int seriesId;
  final int chapterId;
}

DownloadItem? findCompletedSourceDownload({
  required String sourceId,
  required String seriesId,
  required String chapterId,
  required List<DownloadItem> items,
}) {
  DownloadItem? latest;
  for (final item in items) {
    if (item.source != sourceId ||
        item.seriesId != seriesId ||
        item.chapterId != chapterId) {
      continue;
    }
    if (!item.isCompleted || item.localChapterId == null) continue;

    final existing = latest;
    if (existing == null || item.updatedAt.isAfter(existing.updatedAt)) {
      latest = item;
    }
  }
  return latest;
}

ReaderChapter readerChapterFromLibraryDetail(
  ChapterDetail chapter,
  String apiBaseUrl,
) {
  return ReaderChapter(
    id: chapter.id.toString(),
    seriesId: chapter.seriesId.toString(),
    title: chapter.title,
    pageCount: chapter.pageCount,
    mode: ReaderMode.local,
    pages: chapter.pages
        .map(
          (page) => ReaderPage(
            id: page.id.toString(),
            number: page.number,
            imageUrl: readerPageImageUrl(apiBaseUrl, page.id),
            width: page.width,
            height: page.height,
          ),
        )
        .toList(),
  );
}

/// When the online reader fetch fails, fall back to a completed local download.
Future<SourceReaderOfflineHandoff?> resolveSourceReaderOfflineHandoff({
  required DownloadsRepository downloadsRepository,
  required LibraryRepository libraryRepository,
  required SourceReaderChapterArgs args,
}) async {
  final downloadsResult = await downloadsRepository.listDownloads();
  if (downloadsResult.isErr) return null;

  final download = findCompletedSourceDownload(
    sourceId: args.sourceId,
    seriesId: args.seriesId,
    chapterId: args.chapterId,
    items: downloadsResult.value,
  );
  final localChapterId = download?.localChapterId;
  if (localChapterId == null) return null;

  final chapterResult = await libraryRepository.getChapter(localChapterId);
  if (chapterResult.isErr) return null;

  return SourceReaderOfflineHandoff(
    seriesId: chapterResult.value.seriesId,
    chapterId: localChapterId,
  );
}
