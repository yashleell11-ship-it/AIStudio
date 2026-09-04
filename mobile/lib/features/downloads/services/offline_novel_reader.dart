import 'package:manhwamaniacs/core/logging/app_logger.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/novels/models/novel_chapter.dart';

/// Reconstructs a readable [NovelChapter] **entirely from the on-device
/// store**, with no network call at all — the novel half of
/// `offline_reader.dart`, and the phone's whole reason to exist over the web.
///
/// Returns `null` when [id] is not available offline: not downloaded, still
/// mid-download, downloaded as manga rather than prose, or its blob has gone
/// missing (a user deleted it by hand through the Files app). `null` is the
/// caller's signal to fall back to the network error instead of a blank page.
///
/// `prev`/`next` are intentionally absent, exactly as they are for a manga
/// chapter reconstructed offline: without the chapter listing there is no way
/// to know the neighbours, and offering a link the reader cannot follow is
/// worse than not offering one. The chapter still reads end to end.
///
/// Never throws: any failure reaching the store (a platform-channel hiccup, a
/// locked database, a truncated blob) is treated the same as "not available
/// offline" — a broken local store must never be the reason a page that could
/// have shown a real network error shows a store exception instead.
Future<NovelChapter?> buildOfflineNovelChapter(
  DownloadsStore store,
  ChapterIdentity id,
) async {
  try {
    final saved = await store.getChapter(id);
    if (saved == null || saved.state != DownloadChapterState.complete) {
      return null;
    }
    if (!saved.kind.isNovel) return null;

    final stored = await store.readNovelText(id);
    if (stored == null) return null;

    final chapter = NovelChapter.fromStoredJson(
      stored,
      sourceId: id.sourceId,
      seriesKey: id.seriesKey,
      chapterKey: id.chapterKey,
    );
    // A blob that decoded but holds no prose is not a readable chapter; say
    // so rather than opening an empty page with a title on it.
    if (chapter.paragraphs.isEmpty) return null;
    return chapter;
  } catch (error, stackTrace) {
    appLogger.w('Offline novel reconstruction failed', error, stackTrace);
    return null;
  }
}
