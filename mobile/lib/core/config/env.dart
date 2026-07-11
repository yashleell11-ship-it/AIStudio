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

  /// True when this release build ships a non-local https API URL via
  /// `--dart-define=API_URL=...` (e.g. production APK from app.manhwamaniacs.xyz).
  /// Such builds skip the manual setup screen on first launch.
  static bool get hasBakedProductionUrl =>
      isProd &&
      defaultApiUrl.startsWith('https://') &&
      !defaultApiUrl.contains('127.0.0.1') &&
      !defaultApiUrl.contains('localhost');

  /// Whether an insecure `http://` API base URL is permitted.
  ///
  /// Only dev builds may talk to a plain-http backend (local testing);
  /// production/release builds require `https://` so the bearer token is never
  /// transmitted in clear text.
  static bool get allowInsecureBaseUrl => isDev;
}
