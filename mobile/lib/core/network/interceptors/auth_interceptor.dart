import 'package:dio/dio.dart';

/// In-memory holder for the current bearer token and the session-expiry hook.
///
/// The [AuthInterceptor] reads the token synchronously on every request — no
/// secure-storage round-trip per call — and the auth controller keeps this in
/// sync with what is persisted in `SecureStorageService`. Keeping a single
/// long-lived instance app-wide also lets the controller install its
/// [onUnauthorized] handler once, decoupling the network layer from the auth
/// feature (no import cycle).
class AuthTokenStore {
  /// The current bearer token, or null when there is no session.
  String? token;

  void clear() => token = null;

  /// Invoked by the interceptor when a protected request returns 401 mid
  /// session. Defaults to a no-op so a client built without auth wiring (e.g.
  /// the throwaway URL-validation probe) stays inert; the auth controller
  /// installs the real handler at startup.
  void Function() onUnauthorized = _noop;

  static void _noop() {}
}

/// Attaches `Authorization: Bearer <token>` when a token is present and, on a
/// 401 for a protected resource, triggers [AuthTokenStore.onUnauthorized] so
/// the app can drop the stale session and route back to login.
///
/// The public auth entry points and the launch-time `/auth/me` probe are
/// excluded from the 401 handler: a 401 there is an expected credentials /
/// probe outcome handled inline by the caller, not a mid-session expiry — this
/// also avoids re-entrancy while the auth controller is still resolving.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({
    required AuthTokenStore tokenStore,
    required void Function() onUnauthorized,
  })  : _tokenStore = tokenStore,
        _onUnauthorized = onUnauthorized;

  final AuthTokenStore _tokenStore;
  final void Function() _onUnauthorized;

  static const Set<String> _ignored401Paths = {
    '/auth/login',
    '/auth/register',
    '/auth/bootstrap-status',
    '/auth/me',
    '/auth/logout',
  };

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final token = _tokenStore.token;
    if (token != null && token.isNotEmpty) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    if (err.response?.statusCode == 401 &&
        !_ignored401Paths.contains(err.requestOptions.path)) {
      _onUnauthorized();
    }
    handler.next(err);
  }
}
