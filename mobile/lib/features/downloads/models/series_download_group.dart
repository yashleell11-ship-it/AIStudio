import 'package:manhwamaniacs/features/downloads/models/download_item.dart';

class SeriesDownloadGroup {
  const SeriesDownloadGroup({
    required this.key,
    required this.source,
    required this.seriesId,
    required this.seriesTitle,
    required this.items,
    required this.active,
    required this.queued,
    required this.completed,
    required this.failed,
    required this.paused,
  });

  final String key;
  final String source;
  final String seriesId;
  final String seriesTitle;
  final List<DownloadItem> items;
  final int active;
  final int queued;
  final int completed;
  final int failed;
  final int paused;
}
