import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/app.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/test_overrides.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('ManhwaManiacsApp loads with ProviderScope overrides', (tester) async {
    SharedPreferences.setMockInitialValues(testPrefsDefaults());
    final prefs = await SharedPreferences.getInstance();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiBaseUrlOverride(Env.defaultApiUrl),
          sharedPrefsProvider.overrideWithValue(prefs),
          authenticatedAuthOverride(),
          activeProfileOverride(),
          profileSessionReadyOverride(),
        ],
        child: const ManhwaManiacsApp(),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(MaterialApp), findsOneWidget);
    // The app shell renders its bottom-nav destinations; "Library" is the
    // first destination's label. (The Library tab itself shows its error state
    // here because this smoke test provides no library repository override.)
    expect(find.text('Library'), findsWidgets);
  });
}