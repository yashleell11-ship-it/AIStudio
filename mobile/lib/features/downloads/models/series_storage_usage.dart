/// One series' on-device footprint, for the Storage screen's per-series
/// breakdown (ordered by size, largest first).
class SeriesStorageUsage {
  const SeriesStorageUsage({
    required this.sourceId,
    required this.seriesKey,
    required this.seriesTitle,
    required this.bytes,
    required this.chapterCount,
    required this.pinnedChapterCount,
  });

  final String sourceId;
  final String seriesKey;
  final String? seriesTitle;
  final int bytes;
  final int chapterCount;
  final int pinnedChapterCount;

  bool get allPinned => pinnedChapterCount >= chapterCount && chapterCount > 0;
  bool get anyPinned => pinnedChapterCount > 0;
}
