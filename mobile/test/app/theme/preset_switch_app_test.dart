import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/app.dart';
import 'package:manhwamaniacs/app/theme/app_metrics.dart';
import 'package:manhwamaniacs/app/theme/app_palette.dart';
import 'package:manhwamaniacs/app/theme/app_palettes.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/app/theme/preset_controller.dart';
import 'package:manhwamaniacs/app/theme/theme_controller.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// End-to-end proof that a design switch reaches the running app **without a
/// restart**, which was the whole open question in the spec.
///
/// The owner assumed changing the design would need one. It does not: the
/// preset is a ThemeExtension on the same ThemeData the palette rides, so
/// selecting one rebuilds the widget tree exactly the way a palette switch
/// already does — and a restart that loses your place in a chapter would be
/// worse than the thing it replaced.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<ProviderContainer> pumpApp(WidgetTester tester) async {
    SharedPreferences.setMockInitialValues(testPrefsDefaults());
    final prefs = await SharedPreferences.getInstance();
    final container = ProviderContainer(
      overrides: [
        apiBaseUrlOverride(Env.defaultApiUrl),
        sharedPrefsProvider.overrideWithValue(prefs),
        authenticatedAuthOverride(), // user id 1
        activeProfileOverride(), // profile id 1
        ...noDownloadsStoreOverrides(),
        profileSessionReadyOverride(),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const ManhwaManiacsApp(),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    return container;
  }

  ThemeData appTheme(WidgetTester tester) =>
      tester.widget<MaterialApp>(find.byType(MaterialApp)).theme!;

  testWidgets('setPreset reshapes the mounted app and persists per profile',
      (tester) async {
    final container = await pumpApp(tester);
    final prefs = container.read(sharedPrefsProvider);

    expect(appTheme(tester).extension<AppMetrics>(), same(AppPresets.signature));

    await container.read(presetControllerProvider.notifier).setPreset('compact');
    // AnimatedTheme tweens the metrics; settle to the end state.
    await tester.pumpAndSettle();

    final theme = appTheme(tester);
    expect(theme.extension<AppMetrics>(), same(AppPresets.compact));
    expect(theme.dividerTheme.thickness, AppPresets.compact.strokes.divider);
    expect(
      theme.textTheme.bodyMedium?.fontSize,
      AppPresets.compact.text.body.fontSize,
    );
    expect(prefs.getString('mm.preset.u1p1'), 'compact');
  });

  testWidgets('theme and design are independent axes on the live app',
      (tester) async {
    final container = await pumpApp(tester);

    await container.read(presetControllerProvider.notifier).setPreset('editorial');
    await tester.pumpAndSettle();
    // Shape changed; the palette did not.
    expect(appTheme(tester).scaffoldBackgroundColor, AppPalettes.eclipse.bg);
    expect(appTheme(tester).extension<AppMetrics>(), same(AppPresets.editorial));

    await container.read(themeControllerProvider.notifier).setTheme('nord');
    await tester.pumpAndSettle();
    // Colour changed; the preset survived it.
    expect(appTheme(tester).extension<AppPalette>(), same(AppPalettes.nord));
    expect(appTheme(tester).extension<AppMetrics>(), same(AppPresets.editorial));
    expect(appTheme(tester).scaffoldBackgroundColor, AppPalettes.nord.bg);

    final prefs = container.read(sharedPrefsProvider);
    expect(prefs.getString('mm.theme.u1p1'), 'nord');
    expect(prefs.getString('mm.preset.u1p1'), 'editorial');
  });

  testWidgets('every preset builds a mountable app', (tester) async {
    final container = await pumpApp(tester);
    for (final preset in AppPresets.all) {
      await container.read(presetControllerProvider.notifier).setPreset(preset.id);
      await tester.pumpAndSettle();
      expect(
        appTheme(tester).extension<AppMetrics>(),
        same(preset),
        reason: preset.id,
      );
      expect(tester.takeException(), isNull, reason: preset.id);
    }
  });
}
