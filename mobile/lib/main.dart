import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/app.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/core/logging/app_logger.dart';
import 'package:manhwamaniacs/core/network/base_url.dart';
import 'package:manhwamaniacs/core/storage/preferences.dart';
import 'package:manhwamaniacs/core/storage/secure_storage.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final storage = SecureStorageService();
  final savedUrl = await storage.getApiUrl();
  // Upgrade a leftover http:// URL to https:// in release builds so the app
  // never begins a session (and sends its bearer token) over clear text.
  final apiUrl = BaseUrl.normalizeStartup(savedUrl ?? Env.defaultApiUrl);
  appLogger.i('API base URL: $apiUrl  flavor: ${Env.flavor}');

  final prefs = await SharedPreferences.getInstance();
  final preferences = PreferencesService(prefs);
  if (!preferences.setupCompleted) {
    if (savedUrl != null && savedUrl.isNotEmpty) {
      await preferences.setSetupCompleted(true);
    } else if (Env.hasBakedProductionUrl) {
      // Production APK with a baked-in server URL — skip the setup form entirely.
      await storage.setApiUrl(apiUrl);
      await preferences.setSetupCompleted(true);
      appLogger.i('Auto-configured server URL from build: $apiUrl');
    }
  }

  runApp(
    ProviderScope(
      overrides: [
        apiBaseUrlProvider.overrideWith((ref) => apiUrl),
        sharedPrefsProvider.overrideWithValue(prefs),
      ],
      child: const ManhwaManiacsApp(),
    ),
  );
}