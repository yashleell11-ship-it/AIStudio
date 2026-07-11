import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/settings/models/app_changelog.dart';
import 'package:manhwamaniacs/features/settings/providers/app_changelog_provider.dart';
import 'package:manhwamaniacs/features/settings/widgets/whats_new_auto_show.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    // Simulates the app running as build 3 (matches the changelog fixture's
    // "latest" entry below).
    PackageInfo.setMockInitialValues(
      appName: 'ManhwaManiacs',
      packageName: 'com.manhwamaniacs.reader',
      version: '1.2.0',
      buildNumber: '3',
      buildSignature: '',
    );
  });

  Future<void> pumpApp(
    WidgetTester tester, {
    required Map<String, Object> prefsValues,
  }) async {
    SharedPreferences.setMockInitialValues(prefsValues);
    final prefs = await SharedPreferences.getInstance();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sharedPrefsProvider.overrideWithValue(prefs),
          appChangelogProvider.overrideWith((ref) async => const [
                ChangelogRelease(
                  version: '1.2.0',
                  build: 3,
                  date: 'July 2026',
                  highlights: ['Something new'],
                ),
              ],),
        ],
        child: const MaterialApp(
          home: WhatsNewAutoShow(child: Scaffold(body: Text('Home'))),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('shows the sheet when the build increased since last seen',
      (tester) async {
    await pumpApp(tester, prefsValues: {
      'settings_setup_completed': true,
      'settings_last_seen_changelog_build': 2,
    },);

    expect(find.text("What's new"), findsOneWidget);
  });

  testWidgets('does not show on a fresh install (nothing recorded yet)',
      (tester) async {
    await pumpApp(tester, prefsValues: {
      'settings_setup_completed': true,
    },);

    expect(find.text("What's new"), findsNothing);
  });

  testWidgets('does not show when the build has not changed', (tester) async {
    await pumpApp(tester, prefsValues: {
      'settings_setup_completed': true,
      'settings_last_seen_changelog_build': 3,
    },);

    expect(find.text("What's new"), findsNothing);
  });

  testWidgets('does not show before setup is completed', (tester) async {
    await pumpApp(tester, prefsValues: {
      'settings_setup_completed': false,
      'settings_last_seen_changelog_build': 2,
    },);

    expect(find.text("What's new"), findsNothing);
  });

  testWidgets('records the current build even when nothing is shown',
      (tester) async {
    SharedPreferences.setMockInitialValues({
      'settings_setup_completed': true,
      'settings_last_seen_changelog_build': 3,
    });
    final prefs = await SharedPreferences.getInstance();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [sharedPrefsProvider.overrideWithValue(prefs)],
        child: const MaterialApp(
          home: WhatsNewAutoShow(child: Scaffold(body: Text('Home'))),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(prefs.getInt('settings_last_seen_changelog_build'), 3);
  });
}
