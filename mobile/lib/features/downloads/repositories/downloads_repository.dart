import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/models/download_item.dart';
import 'package:manhwamaniacs/features/downloads/models/download_metrics.dart';
import 'package:manhwamaniacs/features/downloads/models/download_settings.dart';
import 'package:manhwamaniacs/features/downloads/models/queue_download_response.dart';

abstract interface class DownloadsRepository {
  Future<Result<List<DownloadItem>>> listDownloads();
  Future<Result<DownloadMetrics>> getMetrics();
  Future<Result<DownloadSettings>> getSettings();
  Future<Result<DownloadSettings>> updateSettings(DownloadSettings settings);

  Future<Result<QueueDownloadResponse>> queueChapters({
    required String sourceId,
    required String seriesId,
    required List<String> chapterIds,
    String? seriesTitle,
    int? priority,
  });

  Future<Result<QueueDownloadResponse>> queueSeries({
    required String sourceId,
    required String seriesId,
    int? priority,
  });

  Future<Result<void>> pauseDownload(int downloadId);
  Future<Result<void>> resumeDownload(int downloadId);
  Future<Result<void>> cancelDownload(int downloadId);
  Future<Result<void>> retryDownload(int downloadId);

  /// Reorder a queued download within its own series' dispatch queue.
  /// [direction] is `"up"` (dispatched sooner) or `"down"` (later).
  Future<Result<void>> moveDownload(int downloadId, {required String direction});

  Future<Result<int>> pauseAll();
  Future<Result<int>> resumeAll();
  Future<Result<int>> cancelAll();

  Future<Result<int>> pauseSeries({
    required String sourceId,
    required String seriesId,
  });

  Future<Result<int>> resumeSeries({
    required String sourceId,
    required String seriesId,
  });

  Future<Result<int>> cancelSeries({
    required String sourceId,
    required String seriesId,
  });
}
