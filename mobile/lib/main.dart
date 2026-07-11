import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/app.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/core/logging/app_logger.dart';
import 'package:manhwamaniacs/core/storage/preferences.dart';
import 'package:manhwamaniacs/core/storage/secure_storage.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final storage = SecureStorageService();
  final savedUrl = await storage.getApiUrl();
  final apiUrl = savedUrl ?? Env.defaultApiUrl;
  appLogger.i('API base URL: $apiUrl  flavor: ${Env.flavor}');

  final prefs = await SharedPreferences.getInstance();
  final preferences = PreferencesService(prefs);
  if (!preferences.setupCompleted && savedUrl != null && savedUrl.isNotEmpty) {
    await preferences.setSetupCompleted(true);
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