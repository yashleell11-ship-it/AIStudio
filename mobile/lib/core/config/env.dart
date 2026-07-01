/// Compile-time environment configuration.
///
/// Supplied via `--dart-define` flags in build scripts / launch configs.
/// Runtime override (user-set server URL) is stored in SecureStorage.
abstract final class Env {
  /// Default API base URL — used only when no runtime override is stored.
  static const String defaultApiUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  /// Identifies the build flavor.
  static const String flavor = String.fromEnvironment(
    'FLAVOR',
    defaultValue: 'dev',
  );

  static bool get isDev => flavor == 'dev';
  static bool get isProd => flavor == 'prod';
}
