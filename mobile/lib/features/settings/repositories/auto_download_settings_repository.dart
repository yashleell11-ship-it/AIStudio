import 'package:manhwamaniacs/core/utils/result.dart';

/// Reads and writes the global `auto_download_enabled` update setting via
/// `GET`/`PUT /updates/settings` (backend/routes/updates.py:93-100).
///
/// This is the master switch for "a series I follow got a new chapter, fetch it
/// without asking": the update scheduler only queues a download when this *and*
/// the per-series `auto_download` flag are on
/// (backend/services/update_service.py:1325-1330).
abstract interface class AutoDownloadSettingsRepository {
  Future<Result<bool>> getAutoDownloadEnabled();

  /// Persist [enabled]; resolves to the value the server stored.
  Future<Result<bool>> setAutoDownloadEnabled(bool enabled);
}
