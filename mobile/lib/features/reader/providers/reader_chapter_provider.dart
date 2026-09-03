import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/services/offline_reader.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

typedef ChapterManifestKey = ({
  String sourceId,
  String seriesKey,
  String chapterKey,
});

/// Fetches the source-native chapter manifest — page list plus adjacent
/// chapter keys — for the manifest-driven library reader. Online-only; see
/// [resolvedReaderChapterProvider] for the offline-aware provider the
/// screens actually watch.
final chapterManifestProvider = FutureProvider.autoDispose
    .family<ChapterManifest, ChapterManifestKey>((ref, key) async {
  final repo = ref.watch(readerRepositoryProvider);
  final result = await repo.manifest(
    sourceId: key.sourceId,
    seriesKey: key.seriesKey,
    chapterKey: key.chapterKey,
  );
  if (result.isErr) throw result.error;
  return result.value;
});

/// A chapter ready to hand to [ReaderContent], plus the bits only the
/// manifest (when reachable) can supply — chapter number for progress pushes,
/// and adjacent keys for prev/next navigation.
///
/// [isOffline] is true when this came from [buildOfflineReaderChapter]
/// instead of a manifest fetch: [prev]/[next] are always `null` in that case
/// (no manifest, no way to know the neighbours), and reader page images
/// resolve entirely from disk (see [ReaderPage.localFile]) — no network
/// involved at all, satisfying the airplane-mode acceptance path.
typedef ResolvedReaderChapter = ({
  ReaderChapter chapter,
  double? chapterNumber,
  String? prev,
  String? next,
  bool isOffline,
});

/// The manifest-driven reader's single data source (spec §3: "the store
/// first, network second — the reader must not know or care which it got").
///
/// Built on [chapterManifestProvider] (not a second, parallel manifest fetch)
/// so every existing override of it keeps working unchanged.
///
/// 1. Fetch the manifest. On success, build the [ReaderChapter] and overlay
///    on-device file paths for any page already downloaded (bandwidth saved,
///    same behaviour online or off).
/// 2. On failure (offline, server unreachable, timed out — any error),
///    fall back to [buildOfflineReaderChapter]: if this exact chapter is
///    fully downloaded, the reader renders it with zero network involvement.
/// 3. Only if *both* fail does this provider surface an error — the original
///    network error, since "chapter not downloaded" piggybacking on it would
///    be a worse message than the real cause.
final resolvedReaderChapterProvider = FutureProvider.autoDispose
    .family<ResolvedReaderChapter, ChapterManifestKey>((ref, key) async {
  final store = ref.watch(downloadsStoreProvider);
  final apiBaseUrl = ref.watch(apiBaseUrlProvider);

  try {
    final manifest = await ref.watch(chapterManifestProvider(key).future);
    final chapter = await overlayLocalPages(
      store,
      manifest.toReaderChapter(apiBaseUrl),
      id: key,
    );
    return (
      chapter: chapter,
      chapterNumber: manifest.chapterNumber,
      prev: manifest.prev,
      next: manifest.next,
      isOffline: false,
    );
  } catch (error) {
    if (store != null) {
      final offline = await buildOfflineReaderChapter(store, key);
      if (offline != null) {
        final saved = await store.getChapter(key);
        return (
          chapter: offline,
          chapterNumber: saved?.chapterNumber,
          prev: null,
          next: null,
          isOffline: true,
        );
      }
    }
    rethrow;
  }
});
