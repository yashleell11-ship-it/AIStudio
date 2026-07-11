import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';

/// Transport policy and normalisation for the API base URL.
///
/// Release/production builds must reach the backend over `https://` so the
/// bearer token is never sent in clear text; dev builds may use `http://` for
/// local testing (see [Env.allowInsecureBaseUrl]).
abstract final class BaseUrl {
  /// Validates a candidate base URL against this build's transport policy.
  /// Returns a [ValidationError] describing the problem, or null when the URL
  /// is acceptable.
  static ValidationError? validate(String url) {
    final trimmed = url.trim();
    if (trimmed.isEmpty) {
      return const ValidationError('Server URL cannot be empty.');
    }
    final uri = Uri.tryParse(trimmed);
    if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
      return const ValidationError(
        'Enter a valid server URL, including http:// or https://.',
      );
    }
    if (uri.scheme != 'http' && uri.scheme != 'https') {
      return const ValidationError('Server URL must use http or https.');
    }
    if (uri.scheme == 'http' && !Env.allowInsecureBaseUrl) {
      return const ValidationError(
        'Insecure http:// is not allowed in this build — use https://.',
      );
    }
    return null;
  }

  /// Normalises the base URL resolved at startup: in builds that forbid
  /// insecure transport an `http://` URL is upgraded to `https://`, so the app
  /// never begins a session pointed at a clear-text endpoint (e.g. a URL left
  /// over from a prior dev build). Returns [url] unchanged when it is already
  /// acceptable or cannot be parsed.
  static String normalizeStartup(String url) {
    final uri = Uri.tryParse(url.trim());
    if (uri == null) return url;
    if (uri.scheme == 'http' && !Env.allowInsecureBaseUrl) {
      return uri.replace(scheme: 'https').toString();
    }
    return url;
  }
}
