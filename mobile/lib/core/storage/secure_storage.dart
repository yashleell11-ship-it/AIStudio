import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Keys for secure storage entries.
abstract final class _Keys {
  static const String apiUrl = 'aistudio_api_url';
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
}
