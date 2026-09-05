import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/logging/app_logger.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/auth/models/auth_response.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/models/auth_user.dart';
import 'package:manhwamaniacs/features/auth/models/bootstrap_status.dart';
import 'package:manhwamaniacs/features/auth/providers/session_offline_provider.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
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
///
/// A session survives an unreachable server. Restoration distinguishes the
/// server *rejecting* the token from never having answered, and on the latter
/// resolves to [AuthAuthenticated] from the cached identity with
/// `sessionOfflineProvider` raised — the token is never touched, because
/// signing back in would need the same server that is down.
class AuthController extends Notifier<AuthState> {
  /// How long the launch-time `/auth/me` probe gets before the app stops
  /// waiting and falls back to the cached session.
  ///
  /// Deliberately far below the client's 15s connect timeout rather than a
  /// lowering of it: an unreachable server on a live LAN blackholes the SYN
  /// instead of refusing it, so without this bound every cold start offline
  /// sits on the splash for the full 15s. Only the *startup* probe is impatient
  /// — real requests keep the generous timeout.
  static const Duration _probeTimeout = Duration(seconds: 3);

  /// The backend's code for "that password is wrong" — a 401, exactly like an
  /// expired session (`services/auth_service.change_password`).
  static const String _invalidCredentialsCode = 'invalid_credentials';

  /// Raised while a request that can answer 401 for a reason *other* than a
  /// dead session is in flight — today only `/auth/change-password`, which
  /// answers 401 `invalid_credentials` when the current password is wrong.
  ///
  /// The Dio interceptor sees a status code and nothing else, so it fires
  /// [onSessionExpired] for both; without this guard one mistyped character
  /// would sign the user out of the app instead of showing "Current password
  /// is incorrect." The request's own result decides which it was
  /// ([changePassword] calls [onSessionExpired] by hand for a genuine one).
  ///
  /// The window is a single in-flight request wide, so at worst an unrelated
  /// request that 401s inside it is not acted on — the next one still is.
  var _expectsCredentialCheck = false;

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

  /// Launch-time restoration, wrapped so that nothing can leave the app latched
  /// on [AuthUnknown].
  ///
  /// The router maps [AuthUnknown] to the splash screen with no timeout and no
  /// other transition, so an unexpected throw anywhere below would freeze the
  /// launch on a branded spinner — which on a sideloaded build is exactly what
  /// a lapsed signing certificate looks like, and therefore the worst possible
  /// failure to be ambiguous about. Dropping to logged-out is recoverable; a
  /// frozen splash is not.
  Future<void> _restore() async {
    try {
      await _restoreSession();
    } catch (error, stackTrace) {
      appLogger.e('Session restore failed unexpectedly', error, stackTrace);
    } finally {
      if (state is AuthUnknown) state = const AuthUnauthenticated();
    }
  }

  Future<void> _restoreSession() async {
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
    final result = await _probeSession();
    if (result.isOk) {
      await _cacheUser(result.value);
      ref.read(sessionOfflineProvider.notifier).markOnline();
      state = AuthAuthenticated(result.value);
      return;
    }
    // Only the server disowning the credential may invalidate a session, and it
    // says so with exactly one thing: a 401 from /auth/me (the backend raises
    // `not_authenticated` and nothing else for a dead session). Every other
    // outcome — a blackholed SYN, a timeout, a 502 from a proxy whose backend
    // is down — says nothing about the token, and clearing it there would
    // strand the user on a login screen that needs the very server that just
    // failed him.
    final error = result.error;
    if (error is ApiError && error.isUnauthorized) {
      await _clearSession();
      state = const AuthUnauthenticated();
      return;
    }
    final cached = _cachedUser();
    if (cached == null) {
      // Unreachable and no cached identity to run on, so there is no session to
      // present. The token deliberately stays in secure storage: the next
      // launch that reaches the server can still validate it.
      appLogger.w('Session restore failed with no cached user', error);
      state = const AuthUnauthenticated();
      return;
    }
    ref.read(sessionOfflineProvider.notifier).markOffline();
    state = AuthAuthenticated(cached);
  }

  /// The launch-time `/auth/me` probe, bounded by [_probeTimeout]. A timeout is
  /// reported as a [TimeoutError] so it lands in the same transport-failure
  /// branch as the interceptor's own timeout/network mapping.
  Future<Result<AuthUser>> _probeSession() async {
    try {
      return await ref.read(authRepositoryProvider).me().timeout(_probeTimeout);
    } on TimeoutException {
      return const Err<AuthUser>(TimeoutError());
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
    await _persistSession(result.value);
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
    String? inviteCode,
  }) async {
    final result = await ref.read(authRepositoryProvider).register(
          username: username,
          password: password,
          email: email,
          displayName: displayName,
          inviteCode: inviteCode,
          remember: remember,
        );
    if (result.isErr) return result.error;
    await _persistSession(result.value);
    state = AuthAuthenticated(result.value.user);
    return null;
  }

  /// Explicit, user-initiated sign-out: revoke the session server-side, then
  /// clear locally. The local token is cleared regardless of the server result.
  Future<void> logout() async {
    await ref.read(authRepositoryProvider).logout();
    await _signOutLocally();
  }

  /// Sign out everywhere: revoke every session for the account — this device's
  /// included — then tear the local session down.
  ///
  /// Unlike [logout] this does NOT clear locally when the server call fails.
  /// The button's whole promise is "no device keeps this account signed in",
  /// and a failed call has revoked nothing; dropping this device alone would
  /// leave the user believing an intruder was signed out while the intruder's
  /// session is still live. So the error is handed back for the screen to show
  /// and the user can retry (plain Sign out is still one screen away).
  ///
  /// What the local teardown clears is the session and only the session: the
  /// bearer token (in-memory and keychain), the cached identity, the active
  /// profile selection and its once-per-session gate, and the cached profile
  /// list. Downloaded chapters are deliberately left on disk — a revoke is not
  /// a data wipe, the blobs cost real bandwidth to re-fetch, and the store is
  /// keyed `u{userId}p{profileId}` (see `downloads_scope.dart`), so no other
  /// account signing in on this device can address them. Removing them stays
  /// where it already lives: Settings -> Storage.
  Future<AppError?> logoutEverywhere() async {
    final result = await ref.read(authRepositoryProvider).logoutAll();
    if (result.isErr) return result.error;
    await _signOutLocally();
    return null;
  }

  /// Change the account password. Null on success, the [AppError] to render on
  /// failure — same contract as [login].
  ///
  /// The session survives: the backend revokes every *other* session and keeps
  /// the one that made the request, so there is no state change on success.
  ///
  /// [_expectsCredentialCheck] is what keeps a mistyped current password from
  /// signing the user out of the app: see its declaration.
  Future<AppError?> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    _expectsCredentialCheck = true;
    final Result<void> result;
    try {
      result = await ref.read(authRepositoryProvider).changePassword(
            currentPassword: currentPassword,
            newPassword: newPassword,
          );
    } finally {
      _expectsCredentialCheck = false;
    }
    if (result.isOk) return null;
    final error = result.error;
    // A 401 that is *not* the wrong-current-password answer really is a dead
    // session, and the guard above swallowed the interceptor's call — so make
    // it by hand rather than leaving the app on a session the server disowned.
    if (error is ApiError &&
        error.isUnauthorized &&
        error.code != _invalidCredentialsCode) {
      onSessionExpired();
    }
    return error;
  }

  /// Reaction to a mid-session 401 raised by the auth interceptor: the token is
  /// already invalid server-side, so only clear locally (no logout call, which
  /// would 401 again) and drop to unauthenticated. Idempotent.
  void onSessionExpired() {
    if (_expectsCredentialCheck) return;
    if (state is AuthUnauthenticated) return;
    unawaited(_clearSession());
    unawaited(ref.read(activeProfileProvider.notifier).clear());
    ref.read(profileSessionReadyProvider.notifier).reset();
    ref.invalidate(profilesProvider);
    state = const AuthUnauthenticated();
  }

  /// Drop this device's session and everything scoped to it, then land on
  /// unauthenticated. Shared by [logout] and [logoutEverywhere] so the two can
  /// never tear down different amounts of state.
  Future<void> _signOutLocally() async {
    await _clearSession();
    await ref.read(activeProfileProvider.notifier).clear();
    ref.read(profileSessionReadyProvider.notifier).reset();
    // Drop the previous account's cached profile list so the next sign-in
    // never briefly renders another user's profiles.
    ref.invalidate(profilesProvider);
    state = const AuthUnauthenticated();
  }

  Future<void> _persistSession(AuthResponse response) async {
    ref.read(authTokenStoreProvider).token = response.token;
    try {
      await ref.read(secureStorageProvider).setAuthToken(response.token);
    } catch (error, stackTrace) {
      // Best-effort, exactly like [_cacheUser]: a keychain write can throw a
      // PlatformException (the plugin turns any non-`noErr` OSStatus into one),
      // and on a re-signed sideloaded build that is a live possibility. The
      // in-memory token set above is what the interceptor actually reads, so
      // the session still works for this launch — only its survival across a
      // restart is lost. Letting this escape instead left `login()` short of
      // `state = AuthAuthenticated(...)` with the sign-in button spinning
      // forever and no error ever shown.
      appLogger.w('Failed to persist the auth token', error, stackTrace);
    }
    await _cacheUser(response.user);
    ref.read(sessionOfflineProvider.notifier).markOnline();
  }

  /// Clears the in-memory token (synchronously, so the very next request drops
  /// the header), the persisted token, and the cached identity — no leftover
  /// blob may let the *next* account's cold start restore this one's session.
  Future<void> _clearSession() async {
    ref.read(authTokenStoreProvider).clear();
    ref.read(sessionOfflineProvider.notifier).markOnline();
    try {
      await ref.read(secureStorageProvider).clearAuthToken();
    } catch (error, stackTrace) {
      // The in-memory token is already gone, so a failed *persistent* delete is
      // survivable and must not be fatal. It was not guarded before, and the
      // caller that matters is [_restore]: a throw there unwound before
      // `state = AuthUnauthenticated()`, latching [AuthUnknown] — which the
      // router maps to the splash screen with no timeout and no other exit.
      // An app frozen on its own splash is indistinguishable from a lapsed
      // sideload certificate, so this one has to degrade quietly.
      appLogger.w('Failed to clear the stored auth token', error, stackTrace);
    }
    try {
      await ref.read(preferencesProvider).clearCachedAuthUser();
    } catch (error, stackTrace) {
      appLogger.w('Failed to clear the cached user', error, stackTrace);
    }
  }

  /// Mirror the confirmed identity into preferences so a later cold start can
  /// resolve a session while the server is unreachable. Best-effort: a failed
  /// cache write must never fail the sign-in that produced it.
  Future<void> _cacheUser(AuthUser user) async {
    try {
      await ref
          .read(preferencesProvider)
          .setCachedAuthUser(jsonEncode(user.toJson()));
    } catch (error, stackTrace) {
      appLogger.w('Failed to cache the authenticated user', error, stackTrace);
    }
  }

  /// The last identity `/auth/me` confirmed, or null when there is none (or it
  /// no longer decodes — a corrupt blob degrades to logged-out, never a crash).
  AuthUser? _cachedUser() {
    try {
      final raw = ref.read(preferencesProvider).cachedAuthUser;
      if (raw == null || raw.isEmpty) return null;
      return AuthUser.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (error, stackTrace) {
      appLogger.w('Failed to read the cached user', error, stackTrace);
      return null;
    }
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
