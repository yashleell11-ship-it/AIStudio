import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';

/// How many downloaded chapters the length estimate is allowed to measure.
///
/// Each one is a small file read, and a series with two hundred downloaded
/// chapters would otherwise do two hundred of them every time its front matter
/// opens. Eight is a sample, and [estimateSeriesLength] reports how many it
/// actually had so the UI can say "from 8 chapters" rather than implying it
/// counted the book.
const int kNovelWordCountSample = 8;

/// Word counts for the chapters of this series the phone actually has.
///
/// **A deliberate divergence from the web.** The web's series page prefetches a
/// handful of chapters to sample their length, which is cheap in a browser tab
/// and warms the server cache anyway. Doing that here would mean a phone
/// provoking several full upstream scrapes every time a book is opened — on a
/// two-vCPU VPS, for a decoration. So the sample is drawn from chapters that
/// are already on the device, and a book with nothing downloaded simply shows
/// no estimate instead of an invented one.
final novelSeriesWordCountsProvider = FutureProvider.autoDispose
    .family<Map<String, int>, SeriesIdentity>((ref, series) async {
  final store = ref.watch(downloadsStoreProvider);
  if (store == null) return const {};

  final rows = (await store.listChapters())
      .where(
        (c) =>
            c.sourceId == series.sourceId &&
            c.seriesKey == series.seriesKey &&
            c.kind.isNovel &&
            c.state == DownloadChapterState.complete,
      )
      .take(kNovelWordCountSample)
      .toList();

  final counts = <String, int>{};
  for (final row in rows) {
    final stored = await store.readNovelText(row.identity);
    final words = (stored?['word_count'] as num?)?.toInt() ?? 0;
    if (words > 0) counts[row.chapterKey] = words;
  }
  return counts;
});
