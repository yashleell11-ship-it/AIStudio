import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/settings/models/backup_status.dart';

/// Database backup export/import against the backend's `/backup/*` API.
///
/// Export has no method here: it's a direct external download (see
/// `BackupScreen`), the same pattern already used for the APK update
/// download, since the app never needs to parse or hold the exported bytes.
abstract interface class BackupRepository {
  Future<Result<BackupStatus>> getStatus();

  /// Upload a backup file at [filePath] to be validated and staged.
  /// The restore only takes effect the next time the backend restarts.
  Future<Result<void>> importBackup(String filePath);

  /// Cancel a previously staged restore before it's applied.
  Future<Result<void>> cancelPendingRestore();
}
