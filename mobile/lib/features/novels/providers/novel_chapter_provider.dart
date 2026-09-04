import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/services/offline_novel_reader.dart';
import 'package:manhwamaniacs/features/novels/models/novel_chapter.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// The opaque `(sourceId, seriesKey, chapterKey)` triple, matching the manga
/// reader's [ChapterManifestKey] so both readers are addressed the same way.
typedef NovelChapterKey = ({
  String sourceId,
  String seriesKey,
  String chapterKey,
});

/// `GET /novels/chapter` — the online payload, which is also the only place
/// `prev`/`next` come from. Kept separate from
/// [resolvedNovelChapterProvider] so the prose and the neighbours can be
/// wanted independently: one fetch, two questions.
final novelChapterPayloadProvider = FutureProvider.autoDispose
    .family<NovelChapter, NovelChapterKey>((ref, key) async {
  final result = await ref.watch(novelsRepositoryProvider).chapter(
        sourceId: key.sourceId,
        seriesKey: key.seriesKey,
        chapterKey: key.chapterKey,
      );
  if (result.isErr) throw result.error;
  return result.value;
});

/// Which chapters sit either side of this one. The store deliberately does
/// not persist them (they are network facts that go stale — see
/// [NovelChapter.toStoredJson]), so this is the only source, and it is
/// resolved *beside* the prose rather than in front of it.
typedef NovelChapterNeighbours = ({String? previousChapterKey, String? nextChapterKey});

final novelChapterNeighboursProvider = FutureProvider.autoDispose
    .family<NovelChapterNeighbours, NovelChapterKey>((ref, key) async {
  final chapter = await ref.watch(novelChapterPayloadProvider(key).future);
  return (
    previousChapterKey: chapter.previousChapterKey,
    nextChapterKey: chapter.nextChapterKey,
  );
});

/// The novel reader's single data source — the prose analog of
/// `resolvedReaderChapterProvider`, and built on the same rule, in the same
/// order (spec R3): **the phone first, the network only for what the phone
/// does not have.**
///
/// 1. **The store.** A downloaded chapter renders with zero network
///    involvement — no request, no proxy, no waiting — even on a perfect
///    connection. The whole chapter is one small blob of text that was
///    already on the phone; asking a server for it first was the reader
///    waiting on the network for its own data.
/// 2. **The network**, when the phone does not have it.
/// 3. **The store again** if that failed, and only then the network error,
///    since "not downloaded" piggybacking on it would be a worse message than
///    the real cause.
///
/// Adjacent keys are not part of this answer offline;
/// [novelChapterNeighboursProvider] supplies them whenever it can, and the
/// reader simply has no next-chapter affordance until it does.
///
/// Offline novel text is the phone's reason to exist over the web, and this
/// is the provider where that is true or not true.
final resolvedNovelChapterProvider = FutureProvider.autoDispose
    .family<NovelChapter, NovelChapterKey>((ref, key) async {
  final store = ref.watch(downloadsStoreProvider);

  if (store != null) {
    final onDisk = await buildOfflineNovelChapter(store, key);
    if (onDisk != null) return onDisk;
  }

  try {
    return await ref.watch(novelChapterPayloadProvider(key).future);
  } catch (error) {
    if (store != null) {
      final offline = await buildOfflineNovelChapter(store, key);
      if (offline != null) return offline;
    }
    rethrow;
  }
});
