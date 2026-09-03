import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/models/bootstrap_status.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/auth/screens/login_screen.dart';
import 'package:manhwamaniacs/features/auth/screens/register_screen.dart';

/// Stub controller that records register() calls and returns a canned result,
/// without touching secure storage or the network.
class _StubAuthController extends AuthController {
  _StubAuthController(this._registerResult);

  final AppError? _registerResult;
  int registerCalls = 0;
  String? lastUsername;
  String? lastEmail;
  String? lastDisplayName;
  String? lastInviteCode;
  bool? lastRemember;

  @override
  AuthState build() => const AuthUnauthenticated();

  @override
  Future<AppError?> register({
    required String username,
    required String password,
    required bool remember,
    String? email,
    String? displayName,
    String? inviteCode,
  }) async {
    registerCalls++;
    lastUsername = username;
    lastEmail = email;
    lastDisplayName = displayName;
    lastInviteCode = inviteCode;
    lastRemember = remember;
    return _registerResult;
  }
}

Widget _wrap({
  required BootstrapStatus status,
  required _StubAuthController controller,
}) {
  final router = GoRouter(
    initialLocation: Routes.register,
    routes: [
      GoRoute(path: Routes.login, builder: (_, __) => const LoginScreen()),
      GoRoute(
        path: Routes.register,
        builder: (_, __) => const RegisterScreen(),
      ),
    ],
  );

  return ProviderScope(
    overrides: [
      authControllerProvider.overrideWith(() => controller),
      bootstrapStatusProvider.overrideWith((ref) => status),
    ],
    child: MaterialApp.router(routerConfig: router),
  );
}

const _openNoInvite =
    BootstrapStatus(needsBootstrap: false, registrationEnabled: true);
const _openInviteRequired = BootstrapStatus(
  needsBootstrap: false,
  registrationEnabled: true,
  inviteCodeRequired: true,
);
// Bootstrap with the invite flag (incorrectly) set — the screen must ignore
// it: the first account on a fresh server never needs an invite code.
const _bootstrapInviteFlagged = BootstrapStatus(
  needsBootstrap: true,
  registrationEnabled: true,
  inviteCodeRequired: true,
);

/// The full form (invite code + inline error) runs taller than the default
/// 800x600 test surface, which leaves the submit button laid out below the
/// visible viewport — still hittable in principle (it's in a scroll view),
/// but its *global* offset then falls outside the render view's bounds, which
/// `tester.tap` refuses. Every test in this file goes through this helper so
/// the surface is always tall enough for the button to be reachable.
Future<void> _pump(
  WidgetTester tester, {
  required BootstrapStatus status,
  required _StubAuthController controller,
}) async {
  await tester.binding.setSurfaceSize(const Size(430, 1400));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(_wrap(status: status, controller: controller));
  await tester.pumpAndSettle();
}

/// `TextField`s appear in document order; the invite-code field only exists
/// between "Confirm password" and "Display name" when required.
Finder _field(int index) => find.byType(TextField).at(index);

Future<void> _fillCore(
  WidgetTester tester, {
  String username = 'reader',
  String password = 'password1',
  String? confirmPassword,
}) async {
  await tester.enterText(_field(0), username);
  await tester.enterText(_field(1), password);
  await tester.enterText(_field(2), confirmPassword ?? password);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('RegisterScreen invite-code visibility', () {
    testWidgets('hidden when the server does not require one', (tester) async {
      final controller = _StubAuthController(null);
      await _pump(tester, status: _openNoInvite, controller: controller);

      expect(find.text('Invite code'), findsNothing);
    });

    testWidgets('shown when the server requires one', (tester) async {
      final controller = _StubAuthController(null);
      await _pump(tester, status: _openInviteRequired, controller: controller);

      expect(find.text('Invite code'), findsOneWidget);
    });

    testWidgets('hidden during bootstrap even if the flag says required',
        (tester) async {
      final controller = _StubAuthController(null);
      await _pump(
        tester,
        status: _bootstrapInviteFlagged,
        controller: controller,
      );

      expect(find.text('Invite code'), findsNothing);
      // The bootstrap CTA is a PrimaryPillButton, which uppercases its label.
      expect(find.text('CREATE THE ADMINISTRATOR ACCOUNT'), findsOneWidget);
    });

    testWidgets('an unknown status (still loading) hides the field',
        (tester) async {
      final controller = _StubAuthController(null);
      final router = GoRouter(
        initialLocation: Routes.register,
        routes: [
          GoRoute(path: Routes.login, builder: (_, __) => const LoginScreen()),
          GoRoute(
            path: Routes.register,
            builder: (_, __) => const RegisterScreen(),
          ),
        ],
      );
      await tester.binding.setSurfaceSize(const Size(430, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authControllerProvider.overrideWith(() => controller),
            // Never resolves — mirrors the brief window before the probe
            // returns.
            bootstrapStatusProvider.overrideWith(
              (ref) => Completer<BootstrapStatus>().future,
            ),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );
      await tester.pump();

      expect(find.text('Invite code'), findsNothing);
    });
  });

  group('RegisterScreen validation', () {
    testWidgets('requires an invite code when the server asks for one',
        (tester) async {
      final controller = _StubAuthController(null);
      await _pump(tester, status: _openInviteRequired, controller: controller);

      await _fillCore(tester);
      await tester.tap(find.text('CREATE ACCOUNT'));
      await tester.pump();

      expect(
        find.text('Enter the invite code for this server.'),
        findsOneWidget,
      );
      expect(controller.registerCalls, 0);
    });

    testWidgets('rejects mismatched passwords', (tester) async {
      final controller = _StubAuthController(null);
      await _pump(tester, status: _openNoInvite, controller: controller);

      await _fillCore(tester, confirmPassword: 'somethingelse1');
      await tester.tap(find.text('CREATE ACCOUNT'));
      await tester.pump();

      expect(find.text("Passwords don't match."), findsOneWidget);
      expect(controller.registerCalls, 0);
    });

    testWidgets('rejects a short password before checking confirmation',
        (tester) async {
      final controller = _StubAuthController(null);
      await _pump(tester, status: _openNoInvite, controller: controller);

      await _fillCore(tester, password: 'short', confirmPassword: 'short');
      await tester.tap(find.text('CREATE ACCOUNT'));
      await tester.pump();

      expect(
        find.text('Password must be at least 8 characters.'),
        findsOneWidget,
      );
      expect(controller.registerCalls, 0);
    });
  });

  group('RegisterScreen happy path', () {
    testWidgets('submits with the invite code when required', (tester) async {
      final controller = _StubAuthController(null);
      await _pump(tester, status: _openInviteRequired, controller: controller);

      await _fillCore(tester);
      await tester.enterText(_field(3), 'HOUSEHOLD-42');
      await tester.tap(find.text('CREATE ACCOUNT'));
      await tester.pump();

      expect(controller.registerCalls, 1);
      expect(controller.lastUsername, 'reader');
      expect(controller.lastInviteCode, 'HOUSEHOLD-42');
      expect(controller.lastRemember, isTrue);
    });

    testWidgets('open registration with no invite code required submits '
        'with a null invite code', (tester) async {
      final controller = _StubAuthController(null);
      await _pump(tester, status: _openNoInvite, controller: controller);

      await _fillCore(tester);
      await tester.tap(find.text('CREATE ACCOUNT'));
      await tester.pump();

      expect(controller.registerCalls, 1);
      expect(controller.lastInviteCode, isNull);
    });

    testWidgets('bootstrap submits with no invite code even when flagged',
        (tester) async {
      final controller = _StubAuthController(null);
      await _pump(
        tester,
        status: _bootstrapInviteFlagged,
        controller: controller,
      );

      await _fillCore(tester, username: 'admin');
      await tester.tap(find.text('CREATE THE ADMINISTRATOR ACCOUNT'));
      await tester.pump();

      expect(controller.registerCalls, 1);
      expect(controller.lastInviteCode, isNull);
    });
  });

  group('RegisterScreen error mapping', () {
    Future<void> submitAndExpect(
      WidgetTester tester, {
      required ApiError result,
      required String expectedMessage,
    }) async {
      final controller = _StubAuthController(result);
      await _pump(tester, status: _openNoInvite, controller: controller);

      await _fillCore(tester);
      await tester.tap(find.text('CREATE ACCOUNT'));
      await tester.pump();
      await tester.pump();

      expect(find.text(expectedMessage), findsOneWidget);
    }

    testWidgets('a wrong invite code says exactly that, not a generic error',
        (tester) async {
      await submitAndExpect(
        tester,
        result: const ApiError(
          statusCode: 403,
          code: 'invite_code_invalid',
          message: 'server-authored message the client should not rely on',
        ),
        expectedMessage:
            "That invite code isn't valid — check it and try again.",
      );
    });

    testWidgets('a missing invite code', (tester) async {
      await submitAndExpect(
        tester,
        result: const ApiError(
          statusCode: 403,
          code: 'invite_code_required',
          message: 'nope',
        ),
        expectedMessage:
            'This server requires an invite code to create an account.',
      );
    });

    testWidgets('registration disabled mid-flow', (tester) async {
      await submitAndExpect(
        tester,
        result: const ApiError(
          statusCode: 403,
          code: 'registration_disabled',
          message: 'nope',
        ),
        expectedMessage: 'Registration is closed on this server.',
      );
    });

    testWidgets('rate limited', (tester) async {
      await submitAndExpect(
        tester,
        result: const ApiError(
          statusCode: 429,
          code: 'rate_limited',
          message: 'nope',
        ),
        expectedMessage: 'Too many attempts — wait a moment and try again.',
      );
    });

    testWidgets('duplicate username', (tester) async {
      await submitAndExpect(
        tester,
        result: const ApiError(
          statusCode: 409,
          code: 'username_taken',
          message: 'nope',
        ),
        expectedMessage: 'That username is already taken.',
      );
    });
  });
}
