import 'package:aistudio_mobile/app/app.dart';
import 'package:aistudio_mobile/core/config/env.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/test_overrides.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('AiStudioApp loads with ProviderScope overrides', (tester) async {
    SharedPreferences.setMockInitialValues(testPrefsDefaults());
    final prefs = await SharedPreferences.getInstance();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiBaseUrlOverride(Env.defaultApiUrl),
          sharedPrefsProvider.overrideWithValue(prefs),
        ],
        child: const AiStudioApp(),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.text('Library'), findsWidgets);
  });
}
