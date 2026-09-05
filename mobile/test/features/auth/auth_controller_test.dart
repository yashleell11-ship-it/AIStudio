import 'dart:async';
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
import 'package:manhwamaniacs/features/auth/providers/session_offline_provider.dart';
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

final _cachedUser = AuthUser(
  id: 9,
  username: 'from-cache',
  isAdmin: true,
  createdAt: DateTime.utc(2023),
);

/// The server is up but says the token is dead.
const _rejected = ApiError(
  statusCode: 401,
  code: 'not_authenticated',
  message: 'expired',
);

/// The server never answered — the failure mode this whole suite is about.
const _unreachable = NetworkError(message: 'blackholed', host: 'nas.local');

class _FakeStorage extends SecureStorageService {
  String? token;

  /// Simulates the keychain refusing a write or a delete. `flutter_secure_
  /// storage` turns any non-`noErr` OSStatus into a `PlatformException`, and on
  /// an iOS build that SideStore re-signs every 7 days that is a live
  /// possibility rather than a theoretical one.
  bool failWrites = false;
  bool failDeletes = false;

  @override
  Future<String?> getAuthToken() async => token;

  @override
  Future<void> setAuthToken(String value) async {
    if (failWrites) throw Exception('keychain write refused');
    token = value;
  }

  @override
  Future<void> clearAuthToken() async {
    if (failDeletes) throw Exception('keychain delete refused');
    token = null;
  }
}

class _FakeAuthRepository implements AuthRepository {
  _FakeAuthRepository({
    this.meResult,
    this.loginResult,
    this.registerResult,
  });

  Result<AuthUser>? meResult;
  Result<AuthResponse>? loginResult;
  Result<AuthResponse>? registerResult;
  int logoutCalls = 0;

  /// Stands in for an unreachable host on a live LAN: the SYN is blackholed, so
  /// the call neither succeeds nor fails — it just never returns.
  bool hangOnMe = false;

  @override
  Future<Result<BootstrapStatus>> bootstrapStatus() async =>
      const Err<BootstrapStatus>(
        ApiError(statusCode: 500, code: 'x', message: 'not used in tests'),
      );

  @override
  Future<Result<AuthResponse>> login({
    required String username,
    required String password,
    bool remember = true,
  }) async =>
      loginResult ??
      const Err<AuthResponse>(
        ApiError(statusCode: 401, code: 'x', message: 'no login result'),
      );

  @override
  Future<Result<AuthResponse>> register({
    required String username,
    required String password,
    String? email,
    String? displayName,
    String? inviteCode,
    bool remember = true,
  }) async =>
      registerResult ??
      const Err<AuthResponse>(
        ApiError(statusCode: 400, code: 'x', message: 'no register result'),
      );

  @override
  Future<Result<void>> logout() async {
    logoutCalls++;
    return const Ok(null);
  }

  @override
  Future<Result<void>> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async =>
      const Err<void>(
        ApiError(statusCode: 500, code: 'x', message: 'not used in tests'),
      );

  @override
  Future<Result<List<UserSession>>> sessions() async =>
      const Err<List<UserSession>>(
        ApiError(statusCode: 500, code: 'x', message: 'not used in tests'),
      );

  @override
  Future<Result<void>> revokeSession(int sessionId) async => const Err<void>(
        ApiError(statusCode: 500, code: 'x', message: 'not used in tests'),
      );

  @override
  Future<Result<void>> logoutAll() async => const Err<void>(
        ApiError(statusCode: 500, code: 'x', message: 'not used in tests'),
      );

  @override
  Future<Result<AuthUser>> me() {
    if (hangOnMe) return Completer<Result<AuthUser>>().future;
    return Future.value(
      meResult ??
          const Err<AuthUser>(
            ApiError(
              statusCode: 401,
              code: 'not_authenticated',
              message: 'nope',
            ),
          ),
    );
  }
}

ProviderContainer _container(
  _FakeAuthRepository repo,
  _FakeStorage storage, {
  List<Override> extra = const [],
}) {
  final container = ProviderContainer(
    overrides: [
      authRepositoryProvider.overrideWithValue(repo),
      secureStorageProvider.overrideWithValue(storage),
      ...extra,
    ],
  );
  addTearDown(container.dispose);
  return container;
}

/// A container wired with real (mock-backed) shared preferences, since every
/// offline path reads or writes the cached-identity blob.
Future<(ProviderContainer, SharedPreferences)> _containerWithPrefs(
  _FakeAuthRepository repo,
  _FakeStorage storage, {
  Map<String, Object> prefs = const {},
}) async {
  SharedPreferences.setMockInitialValues(prefs);
  final instance = await SharedPreferences.getInstance();
  return (
    _container(
      repo,
      storage,
      extra: [sharedPrefsProvider.overrideWithValue(instance)],
    ),
    instance,
  );
}

Map<String, Object> _prefsWithCachedUser() => {
      _cachedUserKey: jsonEncode(_cachedUser.toJson()),
    };

void main() {
  group('AuthController restore', () {
    test('no stored token resolves to unauthenticated', () async {
      final container = _container(_FakeAuthRepository(), _FakeStorage());
      await container.read(authControllerProvider.notifier).restored;
      expect(container.read(authControllerProvider), isA<AuthUnauthenticated>());
    });

    test('valid token is confirmed via /auth/me', () async {
      final storage = _FakeStorage()..token = 'tok';
      final container = _container(
        _FakeAuthRepository(meResult: Ok(_user)),
        storage,
      );
      await container.read(authControllerProvider.notifier).restored;

      final state = container.read(authControllerProvider);
      expect(state, isA<AuthAuthenticated>());
      expect((state as AuthAuthenticated).user.username, 'tester');
      expect(container.read(authTokenStoreProvider).token, 'tok');
    });

    test('rejected token clears the session', () async {
      final storage = _FakeStorage()..token = 'stale';
      final (container, prefs) = await _containerWithPrefs(
        _FakeAuthRepository(meResult: const Err<AuthUser>(_rejected)),
        storage,
        prefs: _prefsWithCachedUser(),
      );
      await container.read(authControllerProvider.notifier).restored;

      expect(container.read(authControllerProvider), isA<AuthUnauthenticated>());
      expect(storage.token, isNull);
      expect(container.read(authTokenStoreProvider).token, isNull);
      // A 401 is the server itself disowning the session, so the cached
      // identity must go too — otherwise the next launch resurrects it offline.
      expect(prefs.getString(_cachedUserKey), isNull);
    });

    test('a confirmed session is cached for the next cold start', () async {
      final (container, prefs) = await _containerWithPrefs(
        _FakeAuthRepository(meResult: Ok(_user)),
        _FakeStorage()..token = 'tok',
      );
      await container.read(authControllerProvider.notifier).restored;

      final raw = prefs.getString(_cachedUserKey);
      expect(raw, isNotNull);
      expect(
        AuthUser.fromJson(jsonDecode(raw!) as Map<String, dynamic>).username,
        'tester',
      );
      expect(container.read(sessionOfflineProvider), isFalse);
    });
  });

  group('AuthController restore with an unreachable server', () {
    test('keeps the token and restores the cached user', () async {
      final storage = _FakeStorage()..token = 'tok';
      final (container, _) = await _containerWithPrefs(
        _FakeAuthRepository(meResult: const Err<AuthUser>(_unreachable)),
        storage,
        prefs: _prefsWithCachedUser(),
      );
      await container.read(authControllerProvider.notifier).restored;

      final state = container.read(authControllerProvider);
      expect(state, isA<AuthAuthenticated>());
      expect((state as AuthAuthenticated).user.username, 'from-cache');
      // The whole point: a transport failure must not touch secure storage —
      // logging back in would need the very server that is down.
      expect(storage.token, 'tok');
      expect(container.read(authTokenStoreProvider).token, 'tok');
      expect(container.read(sessionOfflineProvider), isTrue);
    });

    test('a timeout is treated the same as a refused connection', () async {
      final storage = _FakeStorage()..token = 'tok';
      final (container, _) = await _containerWithPrefs(
        _FakeAuthRepository(meResult: const Err<AuthUser>(TimeoutError())),
        storage,
        prefs: _prefsWithCachedUser(),
      );
      await container.read(authControllerProvider.notifier).restored;

      expect(container.read(authControllerProvider), isA<AuthAuthenticated>());
      expect(storage.token, 'tok');
    });

    test('a blackholed probe resolves well before the 15s connect timeout',
        () async {
      final storage = _FakeStorage()..token = 'tok';
      final (container, _) = await _containerWithPrefs(
        _FakeAuthRepository()..hangOnMe = true,
        storage,
        prefs: _prefsWithCachedUser(),
      );

      final stopwatch = Stopwatch()..start();
      await container.read(authControllerProvider.notifier).restored;
      stopwatch.stop();

      expect(container.read(authControllerProvider), isA<AuthAuthenticated>());
      expect(storage.token, 'tok');
      // The splash must not hang for the client's full connect timeout.
      expect(stopwatch.elapsed, lessThan(const Duration(seconds: 10)));
    });

    test('with no cached user it stays logged out but keeps the token',
        () async {
      final storage = _FakeStorage()..token = 'tok';
      final (container, _) = await _containerWithPrefs(
        _FakeAuthRepository(meResult: const Err<AuthUser>(_unreachable)),
        storage,
      );
      await container.read(authControllerProvider.notifier).restored;

      // There is no identity to present a session with, but the token is still
      // good as far as anyone knows — the next launch can validate it.
      expect(container.read(authControllerProvider), isA<AuthUnauthenticated>());
      expect(storage.token, 'tok');
    });

    test('a 502 from a proxy does not count as a rejection', () async {
      // A reverse proxy in front of a stopped backend answers, but nothing it
      // says is about the token — treating it as one strands the user exactly
      // like an unreachable host does, because login would 502 too.
      final storage = _FakeStorage()..token = 'tok';
      final (container, prefs) = await _containerWithPrefs(
        _FakeAuthRepository(
          meResult: const Err<AuthUser>(
            ApiError(statusCode: 502, code: 'bad_gateway', message: 'down'),
          ),
        ),
        storage,
        prefs: _prefsWithCachedUser(),
      );
      await container.read(authControllerProvider.notifier).restored;

      expect(container.read(authControllerProvider), isA<AuthAuthenticated>());
      expect(storage.token, 'tok');
      expect(prefs.getString(_cachedUserKey), isNotNull);
    });

    test('a corrupt cached blob degrades to logged out', () async {
      final storage = _FakeStorage()..token = 'tok';
      final (container, _) = await _containerWithPrefs(
        _FakeAuthRepository(meResult: const Err<AuthUser>(_unreachable)),
        storage,
        prefs: const {_cachedUserKey: 'not json'},
      );
      await container.read(authControllerProvider.notifier).restored;

      expect(container.read(authControllerProvider), isA<AuthUnauthenticated>());
      expect(storage.token, 'tok');
    });
  });

  group('AuthController login', () {
    test('success persists the token and authenticates', () async {
      final storage = _FakeStorage();
      final container = _container(
        _FakeAuthRepository(
          loginResult: Ok(AuthResponse(user: _user, token: 'fresh')),
        ),
        storage,
      );
      await container.read(authControllerProvider.notifier).restored;

      final error = await container
          .read(authControllerProvider.notifier)
          .login(username: 'tester', password: 'pw', remember: true);

      expect(error, isNull);
      expect(container.read(authControllerProvider), isA<AuthAuthenticated>());
      expect(storage.token, 'fresh');
      expect(container.read(authTokenStoreProvider).token, 'fresh');
    });

    test('success caches the user so the next cold start can run offline',
        () async {
      final (container, prefs) = await _containerWithPrefs(
        _FakeAuthRepository(
          loginResult: Ok(AuthResponse(user: _user, token: 'fresh')),
        ),
        _FakeStorage(),
      );
      await container.read(authControllerProvider.notifier).restored;

      await container
          .read(authControllerProvider.notifier)
          .login(username: 'tester', password: 'pw', remember: true);

      final raw = prefs.getString(_cachedUserKey);
      expect(raw, isNotNull);
      expect(
        AuthUser.fromJson(jsonDecode(raw!) as Map<String, dynamic>).id,
        _user.id,
      );
    });

    test('failure returns the error and stays unauthenticated', () async {
      final storage = _FakeStorage();
      final container = _container(
        _FakeAuthRepository(
          loginResult: const Err<AuthResponse>(
            ApiError(
              statusCode: 401,
              code: 'invalid_credentials',
              message: 'Invalid username or password.',
            ),
          ),
        ),
        storage,
      );
      await container.read(authControllerProvider.notifier).restored;

      final error = await container
          .read(authControllerProvider.notifier)
          .login(username: 'x', password: 'y', remember: true);

      expect(error, isA<ApiError>());
      expect(container.read(authControllerProvider), isA<AuthUnauthenticated>());
      expect(storage.token, isNull);
      expect(container.read(authTokenStoreProvider).token, isNull);
    });
  });

  group('AuthController register', () {
    test('success persists the token and authenticates', () async {
      final storage = _FakeStorage();
      final container = _container(
        _FakeAuthRepository(
          registerResult: Ok(AuthResponse(user: _user, token: 'admintok')),
        ),
        storage,
      );
      await container.read(authControllerProvider.notifier).restored;

      final error = await container
          .read(authControllerProvider.notifier)
          .register(username: 'tester', password: 'password1', remember: true);

      expect(error, isNull);
      expect(container.read(authControllerProvider), isA<AuthAuthenticated>());
      expect(storage.token, 'admintok');
    });
  });

  group('AuthController logout / expiry', () {
    test('logout revokes server-side then clears locally', () async {
      final storage = _FakeStorage()..token = 'tok';
      final repo = _FakeAuthRepository(meResult: Ok(_user));
      // logout() also clears the active reading profile and the cached
      // identity, both of which read sharedPrefsProvider.
      final (container, prefs) = await _containerWithPrefs(repo, storage);
      await container.read(authControllerProvider.notifier).restored;
      expect(container.read(authControllerProvider), isA<AuthAuthenticated>());

      await container.read(authControllerProvider.notifier).logout();

      expect(repo.logoutCalls, 1);
      expect(container.read(authControllerProvider), isA<AuthUnauthenticated>());
      expect(storage.token, isNull);
      expect(container.read(authTokenStoreProvider).token, isNull);
      // No leftover identity for the next account's cold start to restore.
      expect(prefs.getString(_cachedUserKey), isNull);
    });

    test('onSessionExpired drops the session without calling logout', () async {
      // onSessionExpired() also clears the active reading profile, which reads
      // sharedPrefsProvider — provide it so the profile clear can run.
      SharedPreferences.setMockInitialValues(<String, Object>{});
      final prefs = await SharedPreferences.getInstance();
      final storage = _FakeStorage()..token = 'tok';
      final repo = _FakeAuthRepository(meResult: Ok(_user));
      final container = _container(
        repo,
        storage,
        extra: [sharedPrefsProvider.overrideWithValue(prefs)],
      );
      await container.read(authControllerProvider.notifier).restored;
      expect(container.read(authControllerProvider), isA<AuthAuthenticated>());

      container.read(authControllerProvider.notifier).onSessionExpired();

      expect(container.read(authControllerProvider), isA<AuthUnauthenticated>());
      expect(container.read(authTokenStoreProvider).token, isNull);
      await pumpEventQueue();
      expect(repo.logoutCalls, 0);
      expect(storage.token, isNull);
    });
  });

  // The app is sideloaded on iOS and re-signed on the device every 7 days, so
  // a keychain call failing is a real operating condition. None of these may
  // leave the app on a screen it cannot leave — an infinite splash or a
  // permanently spinning sign-in button is indistinguishable from a lapsed
  // signing certificate, which is the one failure the owner must be able to
  // diagnose.
  group('AuthController survives keychain failures', () {
    test('a failed delete still resolves the launch, never latching '
        'AuthUnknown', () async {
      final storage = _FakeStorage()
        ..token = 'stale'
        ..failDeletes = true;
      final (container, _) = await _containerWithPrefs(
        _FakeAuthRepository(meResult: const Err<AuthUser>(_rejected)),
        storage,
        prefs: _prefsWithCachedUser(),
      );

      await container.read(authControllerProvider.notifier).restored;

      // Without the guard the throw unwound past `state = AuthUnauthenticated()`
      // and the router held the app on the splash for the rest of the session.
      expect(container.read(authControllerProvider), isA<AuthUnauthenticated>());
      // The in-memory token is cleared synchronously, so no request carries the
      // credential the server just rejected even though the disk copy survives.
      expect(container.read(authTokenStoreProvider).token, isNull);
    });

    test('a failed write still completes the sign-in it belongs to', () async {
      final storage = _FakeStorage()..failWrites = true;
      final (container, _) = await _containerWithPrefs(
        _FakeAuthRepository(
          loginResult: Ok(AuthResponse(user: _user, token: 'fresh')),
        ),
        storage,
      );
      await container.read(authControllerProvider.notifier).restored;

      final error = await container
          .read(authControllerProvider.notifier)
          .login(username: 'tester', password: 'pw', remember: true);

      expect(error, isNull);
      expect(container.read(authControllerProvider), isA<AuthAuthenticated>());
      // Persistence is what was lost, not the session: the interceptor reads
      // the in-memory token, so this launch works and only a restart signs out.
      expect(container.read(authTokenStoreProvider).token, 'fresh');
      expect(storage.token, isNull);
    });

    test('logout still completes when the delete fails', () async {
      final storage = _FakeStorage()..token = 'tok';
      final repo = _FakeAuthRepository(meResult: Ok(_user));
      final (container, _) = await _containerWithPrefs(repo, storage);
      await container.read(authControllerProvider.notifier).restored;
      expect(container.read(authControllerProvider), isA<AuthAuthenticated>());

      storage.failDeletes = true;
      await container.read(authControllerProvider.notifier).logout();

      expect(repo.logoutCalls, 1);
      // The session is revoked server-side by this point, so a "Log out" that
      // silently did nothing would leave the user on a dead session.
      expect(container.read(authControllerProvider), isA<AuthUnauthenticated>());
      expect(container.read(authTokenStoreProvider).token, isNull);
    });
  });
}
