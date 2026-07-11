import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/storage/secure_storage.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/auth/models/auth_response.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/models/auth_user.dart';
import 'package:manhwamaniacs/features/auth/models/bootstrap_status.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/auth/repositories/auth_repository.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

final _user = AuthUser(
  id: 1,
  username: 'tester',
  isAdmin: false,
  createdAt: DateTime.utc(2024),
);

class _FakeStorage extends SecureStorageService {
  String? token;

  @override
  Future<String?> getAuthToken() async => token;

  @override
  Future<void> setAuthToken(String value) async {
    token = value;
  }

  @override
  Future<void> clearAuthToken() async {
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
  Future<Result<AuthUser>> me() async =>
      meResult ??
      const Err<AuthUser>(
        ApiError(statusCode: 401, code: 'not_authenticated', message: 'nope'),
      );
}

ProviderContainer _container(_FakeAuthRepository repo, _FakeStorage storage) {
  final container = ProviderContainer(
    overrides: [
      authRepositoryProvider.overrideWithValue(repo),
      secureStorageProvider.overrideWithValue(storage),
    ],
  );
  addTearDown(container.dispose);
  return container;
}

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
      final container = _container(
        _FakeAuthRepository(
          meResult: const Err<AuthUser>(
            ApiError(statusCode: 401, code: 'x', message: 'expired'),
          ),
        ),
        storage,
      );
      await container.read(authControllerProvider.notifier).restored;

      expect(container.read(authControllerProvider), isA<AuthUnauthenticated>());
      expect(storage.token, isNull);
      expect(container.read(authTokenStoreProvider).token, isNull);
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
      final container = _container(repo, storage);
      await container.read(authControllerProvider.notifier).restored;
      expect(container.read(authControllerProvider), isA<AuthAuthenticated>());

      await container.read(authControllerProvider.notifier).logout();

      expect(repo.logoutCalls, 1);
      expect(container.read(authControllerProvider), isA<AuthUnauthenticated>());
      expect(storage.token, isNull);
      expect(container.read(authTokenStoreProvider).token, isNull);
    });

    test('onSessionExpired drops the session without calling logout', () async {
      final storage = _FakeStorage()..token = 'tok';
      final repo = _FakeAuthRepository(meResult: Ok(_user));
      final container = _container(repo, storage);
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
}
