import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/services/offline_reader.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

typedef SourceReaderChapterKey = ({String sourceId, String seriesId, String chapterId});

/// Fetches the unified reader payload for an online source chapter.
///
/// Store first, network second (spec §3), same as the manifest-driven
/// library reader's `resolvedReaderChapterProvider` — this is the other of
/// the two call sites: content identity is the same
/// `(sourceId, seriesKey, chapterKey)` triple regardless of which reader
/// reached it, so a chapter downloaded from the source-browse page reads
/// offline exactly like one downloaded from the library page, and vice
/// versa. On a successful online fetch, on-device pages are overlaid onto
/// the result; on failure, the chapter is rebuilt entirely from the store
/// (no network at all) if it is fully downloaded — the airplane-mode/cold
/// start acceptance path. Only when both fail does this surface the
/// original network error.
final sourceReaderChapterProvider = FutureProvider.autoDispose
    .family<ReaderChapter, SourceReaderChapterKey>((ref, key) async {
  final store = ref.watch(downloadsStoreProvider);
  final ChapterIdentity id = (
    sourceId: key.sourceId,
    seriesKey: key.seriesId,
    chapterKey: key.chapterId,
  );

  final repo = ref.watch(sourcesRepositoryProvider);
  final result = await repo.getReaderChapter(
    key.sourceId,
    key.seriesId,
    key.chapterId,
  );
  if (result.isOk) {
    return overlayLocalPages(store, result.value, id: id);
  }

  if (store != null) {
    final offline = await buildOfflineReaderChapter(store, id);
    if (offline != null) return offline;
  }

  throw result.error;
});
