import 'package:aistudio_mobile/core/config/env.dart';
import 'package:aistudio_mobile/core/network/dio_client.dart';
import 'package:aistudio_mobile/core/storage/preferences.dart';
import 'package:aistudio_mobile/core/storage/secure_storage.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

// ── Secure Storage ─────────────────────────────────────────────────────────

final secureStorageProvider = Provider<SecureStorageService>(
  (_) => SecureStorageService(),
  name: 'secureStorage',
);

// ── Shared Preferences ────────────────────────────────────────────────────

/// Must be overridden in ProviderScope with an already-awaited instance.
final sharedPrefsProvider = Provider<SharedPreferences>(
  (_) => throw UnimplementedError('Override sharedPrefsProvider in ProviderScope'),
  name: 'sharedPrefs',
);

final preferencesProvider = Provider<PreferencesService>(
  (ref) => PreferencesService(ref.watch(sharedPrefsProvider)),
  name: 'preferences',
);

// ── API Base URL ───────────────────────────────────────────────────────────

/// The resolved API base URL — runtime value from secure storage or compile-time default.
///
/// Updated live from Settings without requiring an app restart.
final apiBaseUrlProvider = StateProvider<String>(
  (ref) => Env.defaultApiUrl,
  name: 'apiBaseUrl',
);

// ── Dio ───────────────────────────────────────────────────────────────────

final dioProvider = Provider<Dio>(
  (ref) => createDioClient(baseUrl: ref.watch(apiBaseUrlProvider)),
  name: 'dio',
);
