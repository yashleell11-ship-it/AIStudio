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

/// What only the manifest can tell the reader: which chapters sit either side
/// of this one, and the series-wide chapter number progress is filed under.
typedef ChapterNeighbours = ({
  double? chapterNumber,
  String? prev,
  String? next,
});

/// The adjacent-chapter keys for [key], resolved **beside** the content
/// rather than in front of it (spec R3).
///
/// This exists so that [resolvedReaderChapterProvider] never has to await a
/// manifest for a chapter whose pages are already on the phone. The store
/// knows a chapter's bytes but not its neighbours, so a downloaded chapter
/// still wants this eventually — it just must not wait for it to paint. The
/// reader screen watches this separately and folds prev/next in whenever they
/// land (or never, offline, in which case the chapter still reads end to end).
///
/// Built on [chapterManifestProvider], so when the online path *does* need the
/// manifest for its pages there is exactly one fetch shared between the two.
final chapterNeighboursProvider = FutureProvider.autoDispose
    .family<ChapterNeighbours, ChapterManifestKey>((ref, key) async {
  final manifest = await ref.watch(chapterManifestProvider(key).future);
  return (
    chapterNumber: manifest.chapterNumber,
    prev: manifest.prev,
    next: manifest.next,
  );
});

/// A chapter ready to hand to [ReaderContent], plus the bits only the
/// manifest (when reachable) can supply — chapter number for progress pushes,
/// and adjacent keys for prev/next navigation.
///
/// [isOffline] is true when this came from [buildOfflineReaderChapter]
/// instead of a manifest fetch: [prev]/[next] are always `null` in that case
/// (no manifest, no way to know the neighbours — [chapterNeighboursProvider]
/// supplies them later if the network can), and reader page images resolve
/// entirely from disk (see [ReaderPage.localFile]) — no network involved at
/// all, satisfying the airplane-mode acceptance path.
typedef ResolvedReaderChapter = ({
  ReaderChapter chapter,
  double? chapterNumber,
  String? prev,
  String? next,
  bool isOffline,
});

/// The manifest-driven reader's single data source, resolved **disk first**
/// (spec R3: "if a chapter is fully downloaded, render it from disk
/// immediately, without waiting on any network call — even with
/// connectivity").
///
/// The order is the whole point and it is the exact thing a later refactor
/// will want to "helpfully" reverse, so it is pinned by
/// `test/features/downloads/offline_first_resolution_test.dart`:
///
/// 1. **The store.** If this exact chapter is fully downloaded — every page
///    present, every blob file non-empty — build the reader chapter from disk
///    and return. No manifest fetch is awaited, no network call blocks first
///    paint. Adjacent keys arrive out of band via
///    [chapterNeighboursProvider]; progress sync was always out of band.
/// 2. **The network**, for everything the device does not have: the manifest
///    (page URLs, page count, neighbours), with
///    [overlayLocalPages] putting on-device files back over any page that
///    *is* present. That is the partially-downloaded case — the pages on disk
///    render from disk, only the gaps are fetched.
/// 3. **The store again**, if the network failed: a chapter that is complete
///    but whose store read raced a scope change still reads. Reaching here
///    with nothing on disk surfaces the original network error, since
///    "chapter not downloaded" piggybacking on it would be a worse message
///    than the real cause.
///
/// Step 1 makes step 3 unreachable for a fully-downloaded chapter in
/// practice; it is kept because the two are different questions ("is it on
/// disk?" asked before vs. after a failure) and a store that becomes readable
/// only on the second ask should still work.
final resolvedReaderChapterProvider = FutureProvider.autoDispose
    .family<ResolvedReaderChapter, ChapterManifestKey>((ref, key) async {
  final store = ref.watch(downloadsStoreProvider);
  final apiBaseUrl = ref.watch(apiBaseUrlProvider);

  if (store != null) {
    final onDisk = await buildOfflineReaderChapter(store, key);
    if (onDisk != null) {
      final saved = await store.getChapter(key);
      return (
        chapter: onDisk,
        chapterNumber: saved?.chapterNumber,
        prev: null,
        next: null,
        isOffline: true,
      );
    }
  }

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
