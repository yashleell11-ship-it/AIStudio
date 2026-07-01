import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:aistudio_mobile/features/downloads/models/download_metrics.dart';
import 'package:aistudio_mobile/features/downloads/models/download_settings.dart';

abstract interface class DownloadsRepository {
  Future<Result<List<DownloadItem>>> listDownloads();
  Future<Result<DownloadMetrics>> getMetrics();
  Future<Result<DownloadSettings>> getSettings();
  Future<Result<DownloadSettings>> updateSettings(DownloadSettings settings);

  Future<Result<void>> queueChapters({
    required String sourceId,
    required String seriesId,
    required List<String> chapterIds,
    String? seriesTitle,
    int? priority,
  });

  Future<Result<void>> pauseDownload(int downloadId);
  Future<Result<void>> resumeDownload(int downloadId);
  Future<Result<void>> cancelDownload(int downloadId);
  Future<Result<void>> retryDownload(int downloadId);

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
