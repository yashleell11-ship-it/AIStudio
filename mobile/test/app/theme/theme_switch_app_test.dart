import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/app.dart';
import 'package:manhwamaniacs/app/theme/app_palette.dart';
import 'package:manhwamaniacs/app/theme/app_palettes.dart';
import 'package:manhwamaniacs/app/theme/theme_controller.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// End-to-end proof that a theme switch reaches the running app: the
/// MaterialApp's ThemeData (and its AppPalette extension) must follow the
/// controller with no restart, and the choice must land in the signed-in
/// persona's slot.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('setTheme retints the mounted app and persists per profile',
      (tester) async {
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

    ThemeData appTheme() =>
        tester.widget<MaterialApp>(find.byType(MaterialApp)).theme!;

    // Nothing is stored for this persona, so the app opens on the default.
    expect(
      appTheme().scaffoldBackgroundColor,
      AppPalettes.defaultPalette.bg,
    );
    expect(
      appTheme().extension<AppPalette>(),
      same(AppPalettes.defaultPalette),
    );

    await container.read(themeControllerProvider.notifier).setTheme('paper');
    // AnimatedTheme cross-fades the switch; settle to the end state.
    await tester.pumpAndSettle();

    expect(appTheme().scaffoldBackgroundColor, AppPalettes.paper.bg);
    expect(appTheme().extension<AppPalette>(), same(AppPalettes.paper));
    expect(appTheme().brightness, Brightness.light);
    expect(prefs.getString('mm.theme.u1p1'), 'paper');
  });
}
