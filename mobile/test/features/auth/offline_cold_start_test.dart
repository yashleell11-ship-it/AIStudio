import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/app.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/storage/secure_storage.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/auth/models/auth_response.dart';
import 'package:manhwamaniacs/features/auth/models/auth_user.dart';
import 'package:manhwamaniacs/features/auth/models/bootstrap_status.dart';
import 'package:manhwamaniacs/features/auth/repositories/auth_repository.dart';
import 'package:manhwamaniacs/features/auth/screens/login_screen.dart';
import 'package:manhwamaniacs/features/profiles/screens/profile_picker_screen.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// Every auth call fails the way an unreachable host does.
const _unreachable = NetworkError(message: 'blackholed', host: 'nas.local');

class _UnreachableAuthRepository implements AuthRepository {
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

  @override
  Future<Result<void>> logout() async => const Err<void>(_unreachable);

  @override
  Future<Result<AuthUser>> me() async => const Err<AuthUser>(_unreachable);
}

/// A session token left behind by a previous, online launch.
class _StoredTokenStorage extends SecureStorageService {
  String? token = 'stored-token';

  @override
  Future<String?> getAuthToken() async => token;

  @override
  Future<void> setAuthToken(String value) async => token = value;

  @override
  Future<void> clearAuthToken() async => token = null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('a cold start with an unreachable server lands in the app',
      (tester) async {
    final storage = _StoredTokenStorage();
    SharedPreferences.setMockInitialValues(
      testPrefsDefaults({
        'auth_cached_user': jsonEncode(
          AuthUser(
            id: 1,
            username: 'owner',
            isAdmin: true,
            createdAt: DateTime.utc(2024),
          ).toJson(),
        ),
        'mm.active_profile':
            '{"id":1,"name":"Alex","avatar_key":"violet","mood":"romantic"}',
      }),
    );
    final prefs = await SharedPreferences.getInstance();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiBaseUrlOverride(Env.defaultApiUrl),
          sharedPrefsProvider.overrideWithValue(prefs),
          secureStorageProvider.overrideWithValue(storage),
          authRepositoryProvider.overrideWithValue(_UnreachableAuthRepository()),
        ],
        child: const ManhwaManiacsApp(),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 100));

    // Neither dead end: not bounced to a login screen he cannot pass, and not
    // parked on a profile gate that can never list a profile.
    expect(find.byType(LoginScreen), findsNothing);
    expect(find.byType(ProfilePickerScreen), findsNothing);
    // The shell renders (its first bottom-nav destination is "Library"); the
    // tabs themselves show their own error states, since the server is down.
    expect(find.text('Library'), findsWidgets);
    // And the session survived — the token was never the thing at fault.
    expect(storage.token, 'stored-token');
  });
}
