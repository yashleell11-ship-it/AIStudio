import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/logging/app_logger.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/models/bootstrap_status.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// Owns the app-wide authentication state and the bearer-token lifecycle:
/// restores + validates a stored token on launch, persists / clears it on
/// login and logout, and reacts to mid-session 401s surfaced by the interceptor.
///
/// Deliberately a plain Riverpod [Notifier] with an explicit tri-state
/// ([AuthUnknown] / [AuthUnauthenticated] / [AuthAuthenticated]) rather than an
/// `AsyncNotifier`: login and logout never pass through a loading phase (the
/// screens show their own button spinner), so the router never flashes the
/// splash mid-action.
class AuthController extends Notifier<AuthState> {
  late Future<void> _restored;

  /// Completes once the launch-time token restoration has settled. Exposed so
  /// callers (and tests) can await a resolved auth state after a cold start.
  Future<void> get restored => _restored;

  @override
  AuthState build() {
    // Bridge the interceptor's 401 hook to this controller for the app's
    // lifetime, then restore any stored token. Restoration runs off to the side
    // so build() can return the transient [AuthUnknown] synchronously while
    // /auth/me is validated.
    ref.read(authTokenStoreProvider).onUnauthorized = onSessionExpired;
    _restored = _restore();
    return const AuthUnknown();
  }

  Future<void> _restore() async {
    String? token;
    try {
      token = await ref.read(secureStorageProvider).getAuthToken();
    } catch (error, stackTrace) {
      // A secure-storage read can fail (e.g. keystore issues); degrade to
      // logged-out rather than crash the launch.
      appLogger.w('Failed to read stored auth token', error, stackTrace);
      token = null;
    }
    if (token == null || token.isEmpty) {
      state = const AuthUnauthenticated();
      return;
    }
    // Seed the in-memory store so the /auth/me probe carries the token.
    ref.read(authTokenStoreProvider).token = token;
    final result = await ref.read(authRepositoryProvider).me();
    if (result.isOk) {
      state = AuthAuthenticated(result.value);
    } else {
      await _clearToken();
      state = const AuthUnauthenticated();
    }
  }

  /// Attempts login. On success flips state to authenticated and returns null;
  /// on failure leaves the state untouched and returns the [AppError] for the
  /// screen to render inline.
  Future<AppError?> login({
    required String username,
    required String password,
    required bool remember,
  }) async {
    final result = await ref.read(authRepositoryProvider).login(
          username: username,
          password: password,
          remember: remember,
        );
    if (result.isErr) return result.error;
    await _persistSession(result.value.token);
    state = AuthAuthenticated(result.value.user);
    return null;
  }

  /// Creates an account (the first account becomes the admin). Same contract as
  /// [login]: null on success, an [AppError] to display on failure.
  Future<AppError?> register({
    required String username,
    required String password,
    required bool remember,
    String? email,
    String? displayName,
  }) async {
    final result = await ref.read(authRepositoryProvider).register(
          username: username,
          password: password,
          email: email,
          displayName: displayName,
          remember: remember,
        );
    if (result.isErr) return result.error;
    await _persistSession(result.value.token);
    state = AuthAuthenticated(result.value.user);
    return null;
  }

  /// Explicit, user-initiated sign-out: revoke the session server-side, then
  /// clear locally. The local token is cleared regardless of the server result.
  Future<void> logout() async {
    await ref.read(authRepositoryProvider).logout();
    await _clearToken();
    state = const AuthUnauthenticated();
  }

  /// Reaction to a mid-session 401 raised by the auth interceptor: the token is
  /// already invalid server-side, so only clear locally (no logout call, which
  /// would 401 again) and drop to unauthenticated. Idempotent.
  void onSessionExpired() {
    if (state is AuthUnauthenticated) return;
    unawaited(_clearToken());
    state = const AuthUnauthenticated();
  }

  Future<void> _persistSession(String token) async {
    ref.read(authTokenStoreProvider).token = token;
    await ref.read(secureStorageProvider).setAuthToken(token);
  }

  /// Clears the token from the in-memory store (synchronously, so the very next
  /// request drops the header) and from secure storage.
  Future<void> _clearToken() async {
    ref.read(authTokenStoreProvider).clear();
    await ref.read(secureStorageProvider).clearAuthToken();
  }
}

final authControllerProvider = NotifierProvider<AuthController, AuthState>(
  AuthController.new,
  name: 'authController',
);

/// Public pre-auth probe used by the login / register screens to choose between
/// the "create the first admin" and normal flows.
final bootstrapStatusProvider =
    FutureProvider.autoDispose<BootstrapStatus>((ref) async {
  final result = await ref.read(authRepositoryProvider).bootstrapStatus();
  if (result.isErr) throw result.error;
  return result.value;
});
