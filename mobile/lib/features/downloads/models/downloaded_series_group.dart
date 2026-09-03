import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';

/// One series' worth of [SavedChapter] rows for the Downloads screen —
/// every chapter with any on-device footprint (queued, downloading, failed,
/// or complete), grouped by `(sourceId, seriesKey)` and ordered the way the
/// store already orders [DownloadsStore.listChapters] (newest download
/// first).
class DownloadedSeriesGroup {
  const DownloadedSeriesGroup({
    required this.sourceId,
    required this.seriesKey,
    required this.seriesTitle,
    required this.chapters,
  });

  final String sourceId;
  final String seriesKey;
  final String? seriesTitle;
  final List<SavedChapter> chapters;

  int get totalBytes => chapters.fold(0, (sum, c) => sum + c.bytes);

  /// A series is "pinned" once any of its chapters is — pinning always
  /// applies to every chapter at once (see [DownloadsStore.setSeriesPinned]),
  /// but a chapter queued after the pin and not yet resolved could in theory
  /// lag by one write, so this reads defensively rather than requiring all.
  bool get pinned => chapters.any((c) => c.pinned);
}
