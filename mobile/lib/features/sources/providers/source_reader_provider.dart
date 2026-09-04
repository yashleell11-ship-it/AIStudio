import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/services/offline_reader.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

typedef SourceReaderChapterKey = ({String sourceId, String seriesId, String chapterId});

ChapterIdentity _identityOf(SourceReaderChapterKey key) => (
      sourceId: key.sourceId,
      seriesKey: key.seriesId,
      chapterKey: key.chapterId,
    );

/// The raw online reader payload for a source chapter — page URLs *and*
/// adjacent chapter ids, straight from
/// `GET /sources/{source}/series/{series}/chapters/{chapter}/reader`.
///
/// Separated out so the two things that payload carries can be wanted
/// independently: [sourceReaderChapterProvider] wants the pages (and may
/// already have them on disk), [sourceChapterNeighboursProvider] wants only
/// the neighbours. One fetch serves both.
final sourceReaderPayloadProvider = FutureProvider.autoDispose
    .family<ReaderChapter, SourceReaderChapterKey>((ref, key) async {
  final repo = ref.watch(sourcesRepositoryProvider);
  final result = await repo.getReaderChapter(
    key.sourceId,
    key.seriesId,
    key.chapterId,
  );
  if (result.isErr) throw result.error;
  return result.value;
});

/// Which chapters sit either side of this one — resolved beside the content
/// rather than in front of it, so a downloaded chapter never waits on the
/// network to paint (spec R3). Null members mean "the ends of the series";
/// an error here means "not known yet / not knowable offline", which the
/// screen renders as no prev/next affordance rather than as a failure.
typedef SourceChapterNeighbours = ({String? previousChapterId, String? nextChapterId});

final sourceChapterNeighboursProvider = FutureProvider.autoDispose
    .family<SourceChapterNeighbours, SourceReaderChapterKey>((ref, key) async {
  final chapter = await ref.watch(sourceReaderPayloadProvider(key).future);
  return (
    previousChapterId: chapter.previousChapterId,
    nextChapterId: chapter.nextChapterId,
  );
});

/// The source-browse reader's content, resolved **disk first** (spec R3) —
/// the other of the two reader entry points, and deliberately the same order
/// as the library reader's `resolvedReaderChapterProvider`:
///
/// 1. **The store.** A chapter fully downloaded in this scope renders from
///    disk with no network call awaited at all, connectivity or not. Content
///    identity is the same `(sourceId, seriesKey, chapterKey)` triple
///    whichever reader reached it, so a chapter downloaded from the library
///    page reads offline here and vice versa.
/// 2. **The network**, for what the device lacks — with [overlayLocalPages]
///    putting on-device files back over any page that *is* present, so a
///    part-downloaded chapter fetches only its gaps.
/// 3. **The store again** if the network failed, and only then the original
///    network error.
///
/// Adjacent chapter ids are *not* part of this answer when it came from disk
/// (the store knows bytes, not neighbours) — [sourceChapterNeighboursProvider]
/// supplies them out of band.
final sourceReaderChapterProvider = FutureProvider.autoDispose
    .family<ReaderChapter, SourceReaderChapterKey>((ref, key) async {
  final store = ref.watch(downloadsStoreProvider);
  final id = _identityOf(key);

  if (store != null) {
    final onDisk = await buildOfflineReaderChapter(store, id);
    if (onDisk != null) return onDisk;
  }

  try {
    final chapter = await ref.watch(sourceReaderPayloadProvider(key).future);
    return overlayLocalPages(store, chapter, id: id);
  } catch (error) {
    if (store != null) {
      final offline = await buildOfflineReaderChapter(store, id);
      if (offline != null) return offline;
    }
    rethrow;
  }
});
