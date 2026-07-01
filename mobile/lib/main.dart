import 'package:aistudio_mobile/app/app.dart';
import 'package:aistudio_mobile/core/config/env.dart';
import 'package:aistudio_mobile/core/logging/app_logger.dart';
import 'package:aistudio_mobile/core/storage/secure_storage.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Resolve runtime API URL (user-set override > compile-time default).
  final storage = SecureStorageService();
  final savedUrl = await storage.getApiUrl();
  final apiUrl = savedUrl ?? Env.defaultApiUrl;
  appLogger.i('API base URL: $apiUrl  flavor: ${Env.flavor}');

  final prefs = await SharedPreferences.getInstance();

  runApp(
    ProviderScope(
      overrides: [
        apiBaseUrlProvider.overrideWithValue(apiUrl),
        sharedPrefsProvider.overrideWithValue(prefs),
      ],
      child: const AiStudioApp(),
    ),
  );
}
