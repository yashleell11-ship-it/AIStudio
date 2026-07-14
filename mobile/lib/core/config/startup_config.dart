import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/core/network/base_url.dart';
import 'package:manhwamaniacs/core/storage/preferences.dart';
import 'package:manhwamaniacs/core/storage/secure_storage.dart';

/// Resolved API base URL and any persistence side-effects at cold start.
class StartupConfig {
  const StartupConfig({
    required this.apiUrl,
    this.persistApiUrl,
    required this.markSetupCompleted,
  });

  final String apiUrl;

  /// When non-null, overwrite secure storage with the baked production URL.
  final String? persistApiUrl;

  /// When true, mark first-run setup as complete (skip the setup screen).
  final bool markSetupCompleted;
}

/// Pure resolver for startup API configuration — testable without I/O.
///
/// Production APKs with a baked-in https URL always win over a stale runtime
/// override left in secure storage (e.g. localhost from an old dev install).
StartupConfig resolveStartupConfig({
  required String? savedUrl,
  required bool setupCompleted,
  required bool hasBakedProductionUrl,
  required String defaultApiUrl,
}) {
  if (hasBakedProductionUrl) {
    final apiUrl = BaseUrl.normalizeStartup(defaultApiUrl);
    return StartupConfig(
      apiUrl: apiUrl,
      persistApiUrl: savedUrl != apiUrl ? apiUrl : null,
      markSetupCompleted: !setupCompleted,
    );
  }

  final apiUrl = BaseUrl.normalizeStartup(savedUrl ?? defaultApiUrl);
  return StartupConfig(
    apiUrl: apiUrl,
    markSetupCompleted:
        !setupCompleted && savedUrl != null && savedUrl.isNotEmpty,
  );
}

/// Reads secure storage + prefs, applies [resolveStartupConfig], persists
/// migrations, and returns the API base URL for [ProviderScope].
Future<String> applyStartupConfig({
  required SecureStorageService storage,
  required PreferencesService preferences,
  bool? hasBakedProductionUrl,
  String defaultApiUrl = Env.defaultApiUrl,
}) async {
  final savedUrl = await storage.getApiUrl();
  final config = resolveStartupConfig(
    savedUrl: savedUrl,
    setupCompleted: preferences.setupCompleted,
    hasBakedProductionUrl: hasBakedProductionUrl ?? Env.hasBakedProductionUrl,
    defaultApiUrl: defaultApiUrl,
  );

  if (config.persistApiUrl != null) {
    await storage.setApiUrl(config.persistApiUrl!);
  }
  if (config.markSetupCompleted) {
    await preferences.setSetupCompleted(true);
  }

  return config.apiUrl;
}
