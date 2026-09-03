import 'package:manhwamaniacs/core/logging/app_logger.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reader_page.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';

/// Reconstructs a fully renderable [ReaderChapter] **entirely from the
/// on-device store**, with no network call at all — not even a manifest
/// fetch. This is the acceptance path spec §3 describes: airplane mode, cold
/// start, server unreachable, a previously-downloaded chapter still reads
/// end to end.
///
/// Returns `null` when [id] is not fully available offline: not downloaded,
/// still mid-download, or one of its blob files has gone missing (a user
/// deleted it by hand through the Files app — spec §3b). `null` is the
/// caller's signal to fall back to showing the network error instead of a
/// broken reader.
///
/// Chapter/series titles and the chapter number come from the store's own
/// bookkeeping (stamped by the download queue from the manifest at download
/// time) — never re-derived from a network response, because there is none
/// here. `prev`/`next` are intentionally `null`: without a manifest there is
/// no way to know the adjacent chapter keys, so offline navigation is
/// confined to the chapter already open (still satisfies "renders end to
/// end" — it does not promise offline prev/next).
///
/// Never throws: any failure reaching the store itself (a platform-channel
/// hiccup, a locked database) is treated the same as "not available
/// offline" — a broken local store must never be the reason a page that
/// *could* have shown a real network error shows a store exception instead.
Future<ReaderChapter?> buildOfflineReaderChapter(
  DownloadsStore store,
  ChapterIdentity id,
) async {
  try {
    final chapter = await store.getChapter(id);
    if (chapter == null || chapter.state != DownloadChapterState.complete) {
      return null;
    }

    final paths = await store.localPagePaths(id);
    if (paths.length != chapter.pageCount) return null; // an orphaned blob

    final pages = <ReaderPage>[];
    for (var number = 1; number <= chapter.pageCount; number++) {
      final file = paths[number];
      if (file == null) return null;
      pages.add(
        ReaderPage(
          id: '${id.chapterKey}:$number',
          number: number,
          imageUrl: '',
          localFile: file,
        ),
      );
    }

    final title =
        chapterLabel(number: chapter.chapterNumber, title: chapter.title).primary;
    return ReaderChapter(
      id: id.chapterKey,
      seriesId: id.seriesKey,
      title: title,
      pageCount: chapter.pageCount,
      pages: pages,
      sourceId: id.sourceId,
      seriesTitle: chapter.seriesTitle,
    );
  } catch (error, stackTrace) {
    appLogger.w('Offline chapter reconstruction failed', error, stackTrace);
    return null;
  }
}

/// Overlays on-device file paths onto an already-built [chapter] (typically
/// from a successful manifest fetch) for every page already downloaded —
/// "the store first, network second" applies even when online, both to save
/// bandwidth and so a chapter that's already fully on disk never needs the
/// network to re-render a page it already has. A `null` [store] (no active
/// scope) is a no-op — [chapter] is returned unchanged.
///
/// Never throws: a store failure here degrades to "render the online
/// chapter as fetched" rather than turning a successful manifest fetch into
/// a reader error — the overlay is an optimisation, not something the online
/// path may depend on to render at all.
Future<ReaderChapter> overlayLocalPages(
  DownloadsStore? store,
  ReaderChapter chapter, {
  required ChapterIdentity id,
}) async {
  if (store == null) return chapter;
  try {
    final paths = await store.localPagePaths(id);
    if (paths.isEmpty) return chapter;

    return ReaderChapter(
      id: chapter.id,
      seriesId: chapter.seriesId,
      title: chapter.title,
      pageCount: chapter.pageCount,
      sourceId: chapter.sourceId,
      seriesTitle: chapter.seriesTitle,
      previousChapterId: chapter.previousChapterId,
      nextChapterId: chapter.nextChapterId,
      pages: [
        for (final page in chapter.pages)
          paths.containsKey(page.number) ? page.withLocalFile(paths[page.number]!) : page,
      ],
    );
  } catch (error, stackTrace) {
    appLogger.w('Local page overlay failed', error, stackTrace);
    return chapter;
  }
}
