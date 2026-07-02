import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/storage/preferences.dart';
import 'package:aistudio_mobile/core/storage/secure_storage.dart';
import 'package:aistudio_mobile/features/setup/screens/setup_screen.dart';
import 'package:aistudio_mobile/features/settings/providers/settings_provider.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('SetupScreen', () {
    testWidgets('shows validation error when server is unreachable', (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sharedPrefsProvider.overrideWithValue(prefs),
            secureStorageProvider.overrideWithValue(_FakeSecureStorageService()),
            serverValidationProvider.overrideWith(
              (ref) => (_) async => const NetworkError(message: 'offline'),
            ),
          ],
          child: const MaterialApp(home: SetupScreen()),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      expect(find.textContaining('Network error'), findsOneWidget);
      expect(PreferencesService(prefs).setupCompleted, isFalse);
    });

    testWidgets('marks setup complete after successful validation', (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sharedPrefsProvider.overrideWithValue(prefs),
            secureStorageProvider.overrideWithValue(_FakeSecureStorageService()),
            apiBaseUrlOverride('http://127.0.0.1:8000'),
            serverValidationProvider.overrideWith((ref) => (_) async => null),
          ],
          child: MaterialApp(
            home: Builder(
              builder: (context) {
                return SetupScreen();
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'http://192.168.0.10:8000');
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();

      expect(PreferencesService(prefs).setupCompleted, isTrue);
    });
  });
}
