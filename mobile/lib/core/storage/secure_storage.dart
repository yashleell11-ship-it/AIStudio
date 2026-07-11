import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Keys for secure storage entries.
abstract final class _Keys {
  static const String apiUrl = 'manhwamaniacs_api_url';
  static const String authToken = 'manhwamaniacs_auth_token';
}

/// Wrapper around FlutterSecureStorage.
///
/// Stores runtime-configurable values that should survive app restarts
/// but must not be backed up in plain text (e.g. server URL, future tokens).
class SecureStorageService {
  SecureStorageService() : _storage = const FlutterSecureStorage(
        aOptions: AndroidOptions(encryptedSharedPreferences: true),
      );

  final FlutterSecureStorage _storage;

  /// Returns the user-configured API base URL, or null if not set.
  Future<String?> getApiUrl() => _storage.read(key: _Keys.apiUrl);

  /// Persists a custom API base URL.
  Future<void> setApiUrl(String url) => _storage.write(key: _Keys.apiUrl, value: url);

  /// Removes the custom API URL (reverts to compile-time default).
  Future<void> clearApiUrl() => _storage.delete(key: _Keys.apiUrl);

  /// Returns the persisted bearer session token, or null if not logged in.
  Future<String?> getAuthToken() => _storage.read(key: _Keys.authToken);

  /// Persists the bearer session token returned by login / register.
  Future<void> setAuthToken(String token) =>
      _storage.write(key: _Keys.authToken, value: token);

  /// Removes the persisted bearer token (on logout / session expiry).
  Future<void> clearAuthToken() => _storage.delete(key: _Keys.authToken);
}
