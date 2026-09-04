import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/models/known_chapter.dart';
import 'package:manhwamaniacs/features/library/models/series_detail.dart';
import 'package:manhwamaniacs/features/library/utils/followed_series_cache.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// A series page's payload plus where it came from.
///
/// [isOffline] is true when the server could not be reached and this was
/// rebuilt from the offline library cache plus the on-device chapter store:
/// the chapter list is then everything this profile has *downloaded* for the
/// series, not everything the series has, and reading progress is absent
/// because only the server knows it. The screen has to say so — a partial
/// list presented as the whole one is worse than an error.
typedef SeriesDetailView = ({SeriesDetail series, bool isOffline});

/// The library series page's single data source, given the same store-first
/// treatment `resolvedReaderChapterProvider` already gives the reader.
///
/// It used to be network-only, and that was the whole of the "downloaded
/// chapters are unreachable from the library" bug. The reader behind this
/// page has always been able to render a downloaded chapter with no network
/// at all — but the screen in front of it answered a failed fetch with a
/// full-screen error, so the chapters sitting on the phone could not be
/// opened from the library. The door was shut, not the room empty.
///
/// 1. Fetch `GET /library/series/{followed_id}`. On success, that is the
///    answer.
/// 2. On any failure, rebuild from what is on the device: the offline
///    library cache supplies this follow row's identity and metadata, and
///    [DownloadsStore] supplies its chapters.
/// 3. Only when the device cannot answer either does the original network
///    error surface — "you are offline" is a worse message than the real
///    cause when the real cause is a 500.
final seriesDetailProvider =
    FutureProvider.autoDispose.family<SeriesDetailView, int>((ref, seriesId) async {
  final repo = ref.watch(libraryRepositoryProvider);
  // Re-resolves whenever a chapter row's state changes, so a download that
  // finishes while an offline series page is open adds its chapter to the
  // list instead of leaving it behind until the page is reopened.
  ref.watch(downloadQueueControllerProvider.select((s) => s.queueRevision));

  final result = await repo.getSeries(seriesId);
  if (result.isOk) return (series: result.value, isOffline: false);

  final offline = await _offlineSeriesDetail(ref, seriesId);
  if (offline != null) return (series: offline, isOffline: true);
  throw result.error;
});

/// Rebuilds [seriesId]'s page from the device alone. `null` when the device
/// genuinely cannot answer: no active scope, this follow row was never in a
/// synced library page, or nothing of the series was ever downloaded.
///
/// Never throws — a failure reaching the local store must not replace a real
/// network error with a store exception, the same rule
/// `buildOfflineReaderChapter` follows.
Future<SeriesDetail?> _offlineSeriesDetail(Ref ref, int seriesId) async {
  final scopeId = ref.read(activeDownloadsScopeIdProvider);
  final store = ref.read(downloadsStoreProvider);
  if (scopeId == null || store == null) return null;

  final cached = cachedFollowedSeriesById(
    ref.read(sharedPrefsProvider),
    followedSeriesCacheKeyFor(scopeId),
    seriesId,
  );
  if (cached == null) return null;

  try {
    final chapters = await _downloadedChapters(
      store,
      (sourceId: cached.sourceId, seriesKey: cached.seriesKey),
    );
    if (chapters.isEmpty) return null;
    return _detailFromCache(cached, chapters);
  } catch (_) {
    return null;
  }
}

/// Every chapter of [series] the store holds, in reading order, as the
/// chapter rows a series page renders.
///
/// Deliberately every row rather than only the complete ones: a queued or
/// failed chapter is part of what the user asked for, and the row's own
/// download badge already says which are readable right now. Hiding them
/// would answer "where did the rest of my download go" with silence.
Future<List<KnownChapter>> _downloadedChapters(
  DownloadsStore store,
  SeriesIdentity series,
) async {
  final saved = await store.listChapters();
  final mine = [
    for (final chapter in saved)
      if (chapter.sourceId == series.sourceId &&
          chapter.seriesKey == series.seriesKey)
        chapter,
  ]..sort((a, b) => (a.chapterNumber ?? 0).compareTo(b.chapterNumber ?? 0));

  return [
    for (final chapter in mine)
      KnownChapter(
        key: chapter.chapterKey,
        number: chapter.chapterNumber,
        title: chapter.title,
        // Only trustworthy once every page is on disk (see
        // `DownloadChapterState.complete`); 0 mid-download so the row shows
        // no page count rather than a wrong one.
        pageCount: chapter.pageCount > 0 ? chapter.pageCount : null,
      ),
  ];
}

/// The cached follow row, re-dressed as the detail payload the page expects.
///
/// [SeriesDetail.progress] is empty on purpose: per-chapter reading positions
/// live on the server, and inventing them from the store would put a
/// "Reading" pill on a chapter nobody has opened.
SeriesDetail _detailFromCache(FollowedSeries cached, List<KnownChapter> chapters) {
  return SeriesDetail(
    id: cached.id,
    sourceId: cached.sourceId,
    seriesKey: cached.seriesKey,
    title: cached.title,
    coverUrl: cached.coverUrl,
    isFavorite: cached.isFavorite,
    readingStatus: cached.readingStatus,
    notify: cached.notify,
    sortOrder: cached.sortOrder,
    contentRating: cached.contentRating,
    rating: cached.rating,
    matureOverride: cached.matureOverride,
    knownChapters: cached.knownChapters,
    chapterCount: cached.chapterCount,
    lastCheckedAt: cached.lastCheckedAt,
    createdAt: cached.createdAt,
    updatedAt: cached.updatedAt,
    chapters: chapters,
    progress: const {},
  );
}
