import 'package:manhwamaniacs/core/utils/result.dart';

/// Reads and writes the active profile's `mature_content_enabled` preference
/// via `GET`/`PUT /settings`. The value is per-profile on the backend, scoped
/// by the `X-Profile-Id` header the Dio layer attaches to every request.
abstract interface class MatureSettingsRepository {
  /// The active profile's current mature-content flag.
  Future<Result<bool>> getMatureEnabled();

  /// Persist [enabled] for the active profile; resolves to the stored value.
  Future<Result<bool>> setMatureEnabled(bool enabled);
}
