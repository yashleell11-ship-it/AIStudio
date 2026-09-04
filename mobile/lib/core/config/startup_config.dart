import 'dart:async';

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
///
/// [savedUrl] lets the caller start the secure-storage read *before* calling
/// this — on Android that read is EncryptedSharedPreferences over the
/// Keystore, routinely 50-300 ms on a cold start and the slowest single thing
/// between `main()` and the first frame. `main` kicks it off alongside the
/// SharedPreferences load and hands the in-flight future in; omit it and this
/// reads storage itself, which is what the tests do.
Future<String> applyStartupConfig({
  required SecureStorageService storage,
  required PreferencesService preferences,
  bool? hasBakedProductionUrl,
  String defaultApiUrl = Env.defaultApiUrl,
  Future<String?>? savedUrl,
}) async {
  final resolvedSavedUrl = await (savedUrl ?? storage.getApiUrl());
  final config = resolveStartupConfig(
    savedUrl: resolvedSavedUrl,
    setupCompleted: preferences.setupCompleted,
    hasBakedProductionUrl: hasBakedProductionUrl ?? Env.hasBakedProductionUrl,
    defaultApiUrl: defaultApiUrl,
  );

  if (config.persistApiUrl != null) {
    // Deliberately not awaited. This is a one-off migration on a first launch
    // of a baked-production build, nothing on the startup path reads the value
    // back (the resolved URL is passed to ProviderScope directly), and the
    // write is a Keystore round trip. It is idempotent, so a process killed
    // before it lands simply runs it again next launch.
    unawaited(storage.setApiUrl(config.persistApiUrl!));
  }
  if (config.markSetupCompleted) {
    await preferences.setSetupCompleted(true);
  }

  return config.apiUrl;
}
