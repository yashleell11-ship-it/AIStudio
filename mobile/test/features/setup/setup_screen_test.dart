import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/storage/preferences.dart';
import 'package:aistudio_mobile/core/storage/secure_storage.dart';
import 'package:aistudio_mobile/features/setup/screens/setup_screen.dart';
import 'package:aistudio_mobile/features/settings/providers/settings_provider.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

class _FakeSecureStorageService extends SecureStorageService {
  String? storedUrl;

  @override
  Future<String?> getApiUrl() async => storedUrl;

  @override
  Future<void> setApiUrl(String url) async {
    storedUrl = url;
  }
}

GoRouter _setupTestRouter({void Function(String location)? onNavigate}) {
  return GoRouter(
    initialLocation: Routes.setup,
    routes: [
      GoRoute(
        path: Routes.setup,
        builder: (_, __) => const SetupScreen(),
      ),
      GoRoute(
        path: Routes.library,
        builder: (_, state) {
          onNavigate?.call(state.uri.toString());
          return const Scaffold(body: Text('LIBRARY HOME'));
        },
      ),
    ],
  );
}

Widget _wrapSetup({
  required GoRouter router,
  required List<Override> overrides,
}) {
  return ProviderScope(
    overrides: overrides,
    child: MaterialApp.router(routerConfig: router),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('SetupScreen', () {
    testWidgets('shows validation error when server is unreachable', (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      await tester.pumpWidget(
        _wrapSetup(
          router: _setupTestRouter(),
          overrides: [
            sharedPrefsProvider.overrideWithValue(prefs),
            secureStorageProvider.overrideWithValue(_FakeSecureStorageService()),
            serverValidationProvider.overrideWith(
              (ref) => (_) async => const NetworkError(message: 'offline'),
            ),
          ],
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Continue'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.textContaining('Network error'), findsOneWidget);
      expect(PreferencesService(prefs).setupCompleted, isFalse);
      expect(find.byType(SetupScreen), findsOneWidget);
    });

    testWidgets('marks setup complete after successful validation', (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      String? navigatedLocation;

      await tester.pumpWidget(
        _wrapSetup(
          router: _setupTestRouter(onNavigate: (location) => navigatedLocation = location),
          overrides: [
            sharedPrefsProvider.overrideWithValue(prefs),
            secureStorageProvider.overrideWithValue(_FakeSecureStorageService()),
            apiBaseUrlOverride('http://127.0.0.1:8000'),
            serverValidationProvider.overrideWith((ref) => (_) async => null),
          ],
        ),
      );
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'http://192.168.0.10:8000');
      await tester.tap(find.text('Continue'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pumpAndSettle();

      expect(PreferencesService(prefs).setupCompleted, isTrue);
      expect(navigatedLocation, Routes.library);
      expect(find.text('LIBRARY HOME'), findsOneWidget);
      expect(find.byType(SetupScreen), findsNothing);
    });
  });
}
