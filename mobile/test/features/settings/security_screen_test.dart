import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/storage/secure_storage.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/auth/models/auth_response.dart';
import 'package:manhwamaniacs/features/auth/models/auth_user.dart';
import 'package:manhwamaniacs/features/auth/models/bootstrap_status.dart';
import 'package:manhwamaniacs/features/auth/models/user_session.dart';
import 'package:manhwamaniacs/features/auth/repositories/auth_repository.dart';
import 'package:manhwamaniacs/features/settings/screens/security_screen.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

const _unreachable = NetworkError(message: 'blackholed', host: 'nas.local');

UserSession _session({
  required int id,
  required bool current,
  String? userAgent,
}) =>
    UserSession(
      id: id,
      createdAt: DateTime.utc(2026, 9),
      lastUsedAt: DateTime.now().toUtc(),
      expiresAt: DateTime.utc(2026, 10),
      isCurrent: current,
      userAgent: userAgent,
      ipAddress: '10.0.0.4',
    );

class _FakeAuthRepository implements AuthRepository {
  _FakeAuthRepository({List<UserSession>? sessions})
      : _sessions = sessions ??
            [
              _session(id: 1, current: true, userAgent: 'Dart/3.5 (dart:io)'),
              _session(
                id: 2,
                current: false,
                userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 '
                    'Safari/537.36',
              ),
            ];

  final List<UserSession> _sessions;

  Result<void> changePasswordResult = const Ok(null);
  Result<void> logoutAllResult = const Ok(null);

  int changePasswordCalls = 0;
  int logoutAllCalls = 0;
  final revokedIds = <int>[];

  @override
  Future<Result<List<UserSession>>> sessions() async => Ok(_sessions);

  @override
  Future<Result<void>> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    changePasswordCalls++;
    return changePasswordResult;
  }

  @override
  Future<Result<void>> revokeSession(int sessionId) async {
    revokedIds.add(sessionId);
    return const Ok(null);
  }

  @override
  Future<Result<void>> logoutAll() async {
    logoutAllCalls++;
    return logoutAllResult;
  }

  @override
  Future<Result<void>> logout() async => const Ok(null);

  @override
  Future<Result<AuthUser>> me() async => const Err<AuthUser>(_unreachable);

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

Future<void> _pumpSecurity(
  WidgetTester tester,
  _FakeAuthRepository repo,
) async {
  // The screen is three tall cards; give the test a viewport that can hold
  // them so nothing under test is simply not built yet.
  tester.view.physicalSize = const Size(1000, 3000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  SharedPreferences.setMockInitialValues(<String, Object>{});
  final prefs = await SharedPreferences.getInstance();

  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        secureStorageProvider.overrideWithValue(SecureStorageService()),
        authRepositoryProvider.overrideWithValue(repo),
        authenticatedAuthOverride(),
      ],
      child: const MaterialApp(home: SecurityScreen()),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
}

Future<void> _fillPasswords(
  WidgetTester tester, {
  required String current,
  required String next,
  required String confirm,
}) async {
  await tester.enterText(
    find.byKey(const Key('security-current-password')),
    current,
  );
  await tester.enterText(find.byKey(const Key('security-new-password')), next);
  await tester.enterText(
    find.byKey(const Key('security-confirm-password')),
    confirm,
  );
}

Future<void> _tapUpdate(WidgetTester tester) async {
  await tester.tap(find.widgetWithText(FilledButton, 'Update password'));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('sessions list', () {
    testWidgets('names every device and flags this one', (tester) async {
      await _pumpSecurity(tester, _FakeAuthRepository());

      expect(find.text('ManhwaManiacs app'), findsOneWidget);
      expect(find.text('Chrome on Windows'), findsOneWidget);
      expect(find.text('This device'), findsOneWidget);
    });

    // Revoking the current session from here would leave the app holding a
    // token the server has forgotten, discovered only on the next request.
    testWidgets('offers no revoke button for the current session',
        (tester) async {
      await _pumpSecurity(tester, _FakeAuthRepository());

      expect(find.byKey(const Key('revoke-session-1')), findsNothing);
      expect(find.byKey(const Key('revoke-session-2')), findsOneWidget);
    });

    testWidgets('revoking asks first, and cancelling calls nothing',
        (tester) async {
      final repo = _FakeAuthRepository();
      await _pumpSecurity(tester, repo);

      await tester.tap(find.byKey(const Key('revoke-session-2')));
      await tester.pumpAndSettle();
      expect(find.text('Sign out this device?'), findsOneWidget);

      await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
      await tester.pumpAndSettle();

      expect(repo.revokedIds, isEmpty);
    });

    testWidgets('confirming revokes exactly that session', (tester) async {
      final repo = _FakeAuthRepository();
      await _pumpSecurity(tester, repo);

      await tester.tap(find.byKey(const Key('revoke-session-2')));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Sign out'));
      await tester.pumpAndSettle();

      expect(repo.revokedIds, [2]);
    });
  });

  group('change password', () {
    testWidgets('two different new passwords never reach the server',
        (tester) async {
      final repo = _FakeAuthRepository();
      await _pumpSecurity(tester, repo);

      await _fillPasswords(
        tester,
        current: 'old-secret1',
        next: 'new-secret1',
        confirm: 'new-secret2',
      );
      await _tapUpdate(tester);

      expect(find.text("Passwords don't match."), findsOneWidget);
      expect(repo.changePasswordCalls, 0);
    });

    testWidgets('a too-short password is refused in the server\'s own words',
        (tester) async {
      final repo = _FakeAuthRepository();
      await _pumpSecurity(tester, repo);

      await _fillPasswords(
        tester,
        current: 'old-secret1',
        next: 'short',
        confirm: 'short',
      );
      await _tapUpdate(tester);

      expect(
        find.text('Password must be at least 8 characters.'),
        findsOneWidget,
      );
      expect(repo.changePasswordCalls, 0);
    });

    // The server decides how much a failure may disclose; the client repeats it
    // and adds nothing.
    testWidgets('a rejection is shown exactly as the server worded it',
        (tester) async {
      final repo = _FakeAuthRepository()
        ..changePasswordResult = const Err<void>(
          ApiError(
            statusCode: 401,
            code: 'invalid_credentials',
            message: 'Current password is incorrect.',
          ),
        );
      await _pumpSecurity(tester, repo);

      await _fillPasswords(
        tester,
        current: 'wrong',
        next: 'new-secret1',
        confirm: 'new-secret1',
      );
      await _tapUpdate(tester);

      expect(find.text('Current password is incorrect.'), findsOneWidget);
      expect(repo.changePasswordCalls, 1);
    });

    testWidgets('a success clears the fields and says the others were cut off',
        (tester) async {
      final repo = _FakeAuthRepository();
      await _pumpSecurity(tester, repo);

      await _fillPasswords(
        tester,
        current: 'old-secret1',
        next: 'new-secret1',
        confirm: 'new-secret1',
      );
      await _tapUpdate(tester);

      expect(repo.changePasswordCalls, 1);
      expect(
        find.text('Password changed. Your other devices were signed out.'),
        findsOneWidget,
      );
      // No plaintext may sit in a field after the request that needed it.
      for (final field in tester.widgetList<TextField>(find.byType(TextField))) {
        expect(field.controller?.text, isEmpty);
      }
    });
  });

  group('sign out everywhere', () {
    testWidgets('says what it does and does nothing until confirmed',
        (tester) async {
      final repo = _FakeAuthRepository();
      await _pumpSecurity(tester, repo);

      await tester
          .tap(find.widgetWithText(OutlinedButton, 'Sign out everywhere'));
      await tester.pumpAndSettle();

      expect(find.text('Sign out everywhere?'), findsOneWidget);
      // Downloads are expensive to re-fetch, so the dialog promises they stay.
      expect(
        find.textContaining('Downloaded chapters stay on this device.'),
        findsOneWidget,
      );

      await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
      await tester.pumpAndSettle();
      expect(repo.logoutAllCalls, 0);
    });

    testWidgets('confirming revokes every session', (tester) async {
      final repo = _FakeAuthRepository();
      await _pumpSecurity(tester, repo);

      await tester
          .tap(find.widgetWithText(OutlinedButton, 'Sign out everywhere'));
      await tester.pumpAndSettle();
      await tester
          .tap(find.widgetWithText(FilledButton, 'Sign out everywhere'));
      await tester.pumpAndSettle();

      expect(repo.logoutAllCalls, 1);
    });

    testWidgets('a failed call reports it instead of claiming success',
        (tester) async {
      final repo = _FakeAuthRepository()
        ..logoutAllResult = const Err<void>(_unreachable);
      await _pumpSecurity(tester, repo);

      await tester
          .tap(find.widgetWithText(OutlinedButton, 'Sign out everywhere'));
      await tester.pumpAndSettle();
      await tester
          .tap(find.widgetWithText(FilledButton, 'Sign out everywhere'));
      await tester.pumpAndSettle();

      expect(find.text(_unreachable.userMessage), findsOneWidget);
    });
  });
}
