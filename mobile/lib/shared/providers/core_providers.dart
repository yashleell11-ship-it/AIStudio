import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/core/network/dio_client.dart';
import 'package:manhwamaniacs/core/network/interceptors/auth_interceptor.dart';
import 'package:manhwamaniacs/core/storage/preferences.dart';
import 'package:manhwamaniacs/core/storage/secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

// ── Secure Storage ─────────────────────────────────────────────────────────

final secureStorageProvider = Provider<SecureStorageService>(
  (_) => SecureStorageService(),
  name: 'secureStorage',
);

// ── Auth token store ───────────────────────────────────────────────────────

/// Long-lived in-memory holder for the bearer token, read synchronously by the
/// Dio auth interceptor. Kept in sync with secure storage by the auth
/// controller, which also installs its session-expiry handler on it.
final authTokenStoreProvider = Provider<AuthTokenStore>(
  (_) => AuthTokenStore(),
  name: 'authTokenStore',
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
  (ref) {
    final tokenStore = ref.watch(authTokenStoreProvider);
    return createDioClient(
      baseUrl: ref.watch(apiBaseUrlProvider),
      authInterceptor: AuthInterceptor(
        tokenStore: tokenStore,
        onUnauthorized: () => tokenStore.onUnauthorized(),
      ),
    );
  },
  name: 'dio',
);
