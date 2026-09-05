import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/storage/secure_storage.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/auth/models/auth_response.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/models/auth_user.dart';
import 'package:manhwamaniacs/features/auth/models/bootstrap_status.dart';
import 'package:manhwamaniacs/features/auth/models/user_session.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/auth/repositories/auth_repository.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

final _user = AuthUser(
  id: 1,
  username: 'tester',
  isAdmin: false,
  createdAt: DateTime.utc(2024),
);

/// Key `PreferencesService` caches the last confirmed identity under.
const _cachedUserKey = 'auth_cached_user';

/// What `POST /auth/change-password` answers when the *current* password is
/// wrong — a 401, indistinguishable on the wire from an expired session.
const _wrongPassword = ApiError(
  statusCode: 401,
  code: 'invalid_credentials',
  message: 'Current password is incorrect.',
);

/// What every protected endpoint answers when the session really is dead.
const _deadSession = ApiError(
  statusCode: 401,
  code: 'not_authenticated',
  message: 'Authentication required.',
);

const _unreachable = NetworkError(message: 'blackholed', host: 'nas.local');

class _FakeStorage extends SecureStorageService {
  String? token;

  @override
  Future<String?> getAuthToken() async => token;

  @override
  Future<void> setAuthToken(String value) async => token = value;

  @override
  Future<void> clearAuthToken() async => token = null;
}

class _FakeAuthRepository implements AuthRepository {
  Result<void> changePasswordResult = const Ok(null);
  Result<void> logoutAllResult = const Ok(null);

  int changePasswordCalls = 0;
  int logoutAllCalls = 0;
  int logoutCalls = 0;
  String? sentCurrentPassword;
  String? sentNewPassword;

  /// Stands in for the Dio auth interceptor, which fires the session-expiry
  /// hook on ANY 401 *before* the caller ever sees the error — the exact
  /// ordering that makes a mistyped password dangerous.
  void Function()? on401;

  void _fire401(AppError error) {
    if (error is ApiError && error.isUnauthorized) on401?.call();
  }

  @override
  Future<Result<void>> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    changePasswordCalls++;
    sentCurrentPassword = currentPassword;
    sentNewPassword = newPassword;
    final result = changePasswordResult;
    if (result.isErr) _fire401(result.error);
    return result;
  }

  @override
  Future<Result<void>> logoutAll() async {
    logoutAllCalls++;
    final result = logoutAllResult;
    if (result.isErr) _fire401(result.error);
    return result;
  }

  @override
  Future<Result<void>> logout() async {
    logoutCalls++;
    return const Ok(null);
  }

  @override
  Future<Result<AuthUser>> me() async => Ok(_user);

  @override
  Future<Result<List<UserSession>>> sessions() async => const Ok([]);

  @override
  Future<Result<void>> revokeSession(int sessionId) async => const Ok(null);

  @override
  Future<Result<BootstrapStatus>> bootstrapStatus() async =>
      const Err<BootstrapStatus>(_unreachable);

  @override
  Future<Result<AuthResponse>> login({
    required String username,
    required String password,
    bool remember = true,
  }) async =>
      const Err<AuthResponse>(_unreachable);

  @override
  Future<Result<AuthResponse>> register({
    required String username,
    required String password,
    String? email,
    String? displayName,
    String? inviteCode,
    bool remember = true,
  }) async =>
      const Err<AuthResponse>(_unreachable);
}

/// A container already holding a live, restored session — the state every test
/// here starts from.
Future<(ProviderContainer, SharedPreferences, _FakeStorage)> _signedIn(
  _FakeAuthRepository repo,
) async {
  SharedPreferences.setMockInitialValues(<String, Object>{
    _cachedUserKey: jsonEncode(_user.toJson()),
  });
  final prefs = await SharedPreferences.getInstance();
  final storage = _FakeStorage()..token = 'live-token';
  final container = ProviderContainer(
    overrides: [
      authRepositoryProvider.overrideWithValue(repo),
      secureStorageProvider.overrideWithValue(storage),
      sharedPrefsProvider.overrideWithValue(prefs),
    ],
  );
  addTearDown(container.dispose);
  await container.read(authControllerProvider.notifier).restored;
  expect(container.read(authControllerProvider), isA<AuthAuthenticated>());
  // Wire the fake to the same hook the real interceptor drives.
  repo.on401 = () => container.read(authTokenStoreProvider).onUnauthorized();
  return (container, prefs, storage);
}

void main() {
  group('AuthController.changePassword', () {
    // The whole point of the guard in AuthController: /auth/change-password is
    // not in the interceptor's ignore list, so its 401 reaches the session
    // handler. Without the guard, one wrong character on this form signs the
    // user out of the app instead of saying which field is wrong.
    test('a wrong current password does not sign the user out', () async {
      final repo = _FakeAuthRepository()
        ..changePasswordResult = const Err<void>(_wrongPassword);
      final (container, prefs, storage) = await _signedIn(repo);

      final error = await container
          .read(authControllerProvider.notifier)
          .changePassword(currentPassword: 'wrong', newPassword: 'new-secret1');

      expect(error, _wrongPassword);
      expect(container.read(authControllerProvider), isA<AuthAuthenticated>());
      expect(container.read(authTokenStoreProvider).token, 'live-token');
      expect(storage.token, 'live-token');
      expect(prefs.getString(_cachedUserKey), isNotNull);
    });

    // ...and the guard must not swallow the real thing.
    test('a session that died mid-form still signs the user out', () async {
      final repo = _FakeAuthRepository()
        ..changePasswordResult = const Err<void>(_deadSession);
      final (container, _, storage) = await _signedIn(repo);

      final error = await container
          .read(authControllerProvider.notifier)
          .changePassword(currentPassword: 'old', newPassword: 'new-secret1');

      expect(error, _deadSession);
      expect(container.read(authControllerProvider), isA<AuthUnauthenticated>());
      expect(container.read(authTokenStoreProvider).token, isNull);
      expect(storage.token, isNull);
    });

    test('a successful change keeps this device signed in', () async {
      final repo = _FakeAuthRepository();
      final (container, _, storage) = await _signedIn(repo);

      final error = await container
          .read(authControllerProvider.notifier)
          .changePassword(
            currentPassword: 'old-secret1',
            newPassword: 'new-secret1',
          );

      expect(error, isNull);
      // The backend revokes every OTHER session and keeps this one, so nothing
      // local may be torn down here.
      expect(container.read(authControllerProvider), isA<AuthAuthenticated>());
      expect(storage.token, 'live-token');
      expect(repo.logoutCalls, 0);
      expect(repo.sentCurrentPassword, 'old-secret1');
      expect(repo.sentNewPassword, 'new-secret1');
    });

    // The guard is one request wide: a later 401 must be acted on as usual.
    test('the expiry guard is lifted once the request is done', () async {
      final repo = _FakeAuthRepository();
      final (container, _, storage) = await _signedIn(repo);
      await container.read(authControllerProvider.notifier).changePassword(
            currentPassword: 'old-secret1',
            newPassword: 'new-secret1',
          );

      container.read(authTokenStoreProvider).onUnauthorized();

      expect(container.read(authControllerProvider), isA<AuthUnauthenticated>());
      expect(storage.token, isNull);
    });
  });

  group('AuthController.logoutEverywhere', () {
    test('revokes on the server, then tears this device down', () async {
      final repo = _FakeAuthRepository();
      final (container, prefs, storage) = await _signedIn(repo);

      final error =
          await container.read(authControllerProvider.notifier).logoutEverywhere();

      expect(error, isNull);
      expect(repo.logoutAllCalls, 1);
      expect(container.read(authControllerProvider), isA<AuthUnauthenticated>());
      expect(container.read(authTokenStoreProvider).token, isNull);
      expect(storage.token, isNull);
      // No leftover identity for the next account's cold start to restore.
      expect(prefs.getString(_cachedUserKey), isNull);
    });

    // "Sign out everywhere" that reached nobody has revoked nothing. Dropping
    // this device alone would tell the user every session was killed while the
    // one they are afraid of is still live.
    test('a failed call leaves the local session alone and reports why',
        () async {
      final repo = _FakeAuthRepository()
        ..logoutAllResult = const Err<void>(_unreachable);
      final (container, _, storage) = await _signedIn(repo);

      final error =
          await container.read(authControllerProvider.notifier).logoutEverywhere();

      expect(error, _unreachable);
      expect(container.read(authControllerProvider), isA<AuthAuthenticated>());
      expect(container.read(authTokenStoreProvider).token, 'live-token');
      expect(storage.token, 'live-token');
    });
  });
}
