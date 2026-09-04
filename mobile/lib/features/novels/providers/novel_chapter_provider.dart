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

/// The novel reader's single data source — the prose analog of
/// `resolvedReaderChapterProvider`, and built on the same rule: **the store
/// first, network second, and the reader must not know or care which it got.**
///
/// 1. Fetch `/novels/chapter`. That is the copy with `prev`/`next` on it, so a
///    reachable server always wins — it is the only way to keep reading past
///    the chapter in hand.
/// 2. On any failure (offline, server down, timed out), fall back to the
///    on-device store. A downloaded chapter then renders with **zero** network
///    involvement: no manifest, no images, no proxy — the whole chapter is one
///    small blob of text that was already on the phone.
/// 3. Only if both fail does this surface an error, and it surfaces the
///    *network* one — "not downloaded" piggybacking on it would be a worse
///    message than the real cause.
///
/// Offline novel text is the phone's reason to exist over the web, and this is
/// the provider where that is true or not true.
final resolvedNovelChapterProvider = FutureProvider.autoDispose
    .family<NovelChapter, NovelChapterKey>((ref, key) async {
  final result = await ref.read(novelsRepositoryProvider).chapter(
        sourceId: key.sourceId,
        seriesKey: key.seriesKey,
        chapterKey: key.chapterKey,
      );
  if (result.isOk) return result.value;

  final store = ref.read(downloadsStoreProvider);
  if (store != null) {
    final offline = await buildOfflineNovelChapter(store, key);
    if (offline != null) return offline;
  }
  throw result.error;
});
