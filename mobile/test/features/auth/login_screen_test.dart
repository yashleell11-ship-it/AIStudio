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

import '../../support/test_overrides.dart';

/// Stub controller that records login attempts and returns a canned result,
/// without touching secure storage or the network.
class _StubAuthController extends AuthController {
  _StubAuthController(this._loginResult);

  final AppError? _loginResult;
  int loginCalls = 0;
  String? lastUsername;
  bool? lastRemember;

  @override
  AuthState build() => const AuthUnauthenticated();

  @override
  Future<AppError?> login({
    required String username,
    required String password,
    required bool remember,
  }) async {
    loginCalls++;
    lastUsername = username;
    lastRemember = remember;
    return _loginResult;
  }
}

Widget _wrap({
  required BootstrapStatus status,
  required _StubAuthController controller,
  List<Override> extraOverrides = const [],
}) {
  final router = GoRouter(
    initialLocation: Routes.login,
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
      ...extraOverrides,
    ],
    child: MaterialApp.router(routerConfig: router),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const openStatus =
      BootstrapStatus(needsBootstrap: false, registrationEnabled: true);

  group('LoginScreen', () {
    testWidgets('shows a validation message when fields are empty',
        (tester) async {
      final controller = _StubAuthController(null);
      await tester.pumpWidget(
        _wrap(status: openStatus, controller: controller),
      );
      await tester.pumpAndSettle();

      // Submit is now a PrimaryPillButton, which uppercases its label.
      await tester.tap(find.text('SIGN IN'));
      await tester.pump();

      expect(find.text('Enter your username and password.'), findsOneWidget);
      expect(controller.loginCalls, 0);
    });

    testWidgets('submits credentials to the controller', (tester) async {
      final controller = _StubAuthController(null);
      await tester.pumpWidget(
        _wrap(status: openStatus, controller: controller),
      );
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField).at(0), 'reader');
      await tester.enterText(find.byType(TextField).at(1), 'password1');
      // Submit is now a PrimaryPillButton, which uppercases its label.
      await tester.tap(find.text('SIGN IN'));
      await tester.pump();

      expect(controller.loginCalls, 1);
      expect(controller.lastUsername, 'reader');
      expect(controller.lastRemember, isTrue);
    });

    testWidgets('surfaces the server error inline', (tester) async {
      final controller = _StubAuthController(
        const ApiError(
          statusCode: 401,
          code: 'invalid_credentials',
          message: 'Invalid username or password.',
        ),
      );
      await tester.pumpWidget(
        _wrap(status: openStatus, controller: controller),
      );
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField).at(0), 'reader');
      await tester.enterText(find.byType(TextField).at(1), 'wrong');
      // Submit is now a PrimaryPillButton, which uppercases its label.
      await tester.tap(find.text('SIGN IN'));
      await tester.pump();
      await tester.pump();

      expect(find.text('Invalid username or password.'), findsOneWidget);
    });

    testWidgets('shows the configured server host for diagnostics',
        (tester) async {
      final controller = _StubAuthController(null);
      await tester.pumpWidget(
        _wrap(
          status: openStatus,
          controller: controller,
          extraOverrides: [
            apiBaseUrlOverride('https://app.manhwamaniacs.xyz'),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Server: app.manhwamaniacs.xyz'), findsOneWidget);
    });

    testWidgets('guides to create the first account when bootstrapping',
        (tester) async {
      final controller = _StubAuthController(null);
      await tester.pumpWidget(
        _wrap(
          status: const BootstrapStatus(
            needsBootstrap: true,
            registrationEnabled: true,
          ),
          controller: controller,
        ),
      );
      await tester.pumpAndSettle();

      // Bootstrap CTA is a PrimaryPillButton, which uppercases its label.
      expect(find.text('CREATE THE FIRST ACCOUNT'), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
    });

    testWidgets('shows "Create an account" when registration is open',
        (tester) async {
      final controller = _StubAuthController(null);
      await tester.pumpWidget(
        _wrap(status: openStatus, controller: controller),
      );
      await tester.pumpAndSettle();

      expect(find.text('Create an account'), findsOneWidget);
    });

    testWidgets('hides "Create an account" when registration is closed',
        (tester) async {
      final controller = _StubAuthController(null);
      await tester.pumpWidget(
        _wrap(
          status: const BootstrapStatus(
            needsBootstrap: false,
            registrationEnabled: false,
          ),
          controller: controller,
        ),
      );
      await tester.pumpAndSettle();

      // Never a dead button — closed registration renders no affordance for
      // it at all, not a disabled one.
      expect(find.text('Create an account'), findsNothing);
    });
  });
}
