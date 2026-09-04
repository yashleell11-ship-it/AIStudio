import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/sources/providers/sources_provider.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_chapter_sort.dart';

/// Every chapter of a series, oldest first — the list "Read all" (spec R2) is
/// read against.
///
/// With it the reader knows what follows any chapter without a round trip per
/// boundary, which is what lets a 300-chapter series be one scroll. Without it
/// (still loading, or a source that would not answer) the reader falls back to
/// asking per chapter, which is exactly the ordinary read — so Read-all
/// degrades into the normal reader rather than into an error.
///
/// Keyed by source-native identity, so it serves the library reader and the
/// source-browse reader from one entry: a series is `(sourceId, seriesKey)`
/// wherever it was reached from.
final seriesReadingOrderProvider = FutureProvider.autoDispose
    .family<List<String>, ({String sourceId, String seriesId})>((ref, key) async {
  final detail = await ref.watch(sourceSeriesDetailProvider(key).future);
  return [
    for (final chapter in sortSeriesChapters(
      detail.chapters,
      numberOf: (chapter) => chapter.number,
      order: SeriesChapterSortOrder.oldest,
    ))
      chapter.id,
  ];
});
