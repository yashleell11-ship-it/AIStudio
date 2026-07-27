import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/app.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/core/config/startup_config.dart';
import 'package:manhwamaniacs/core/logging/app_logger.dart';
import 'package:manhwamaniacs/core/platform/system_ui.dart';
import 'package:manhwamaniacs/core/storage/preferences.dart';
import 'package:manhwamaniacs/core/storage/secure_storage.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Android: edge-to-edge with auto-hiding nav buttons (swipe up to reveal).
  // iOS: plain edge-to-edge — see `restingSystemUiMode` for why the immersive
  // modes are Android-only there.
  await applyRestingSystemUiMode();

  final storage = SecureStorageService();
  final prefs = await SharedPreferences.getInstance();
  final preferences = PreferencesService(prefs);
  final apiUrl = await applyStartupConfig(
    storage: storage,
    preferences: preferences,
  );
  appLogger.i('API base URL: $apiUrl  flavor: ${Env.flavor}');

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