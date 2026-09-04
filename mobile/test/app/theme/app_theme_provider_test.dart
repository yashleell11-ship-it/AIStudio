import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/theme/app_theme.dart';
import 'package:manhwamaniacs/app/theme/app_theme_provider.dart';
import 'package:manhwamaniacs/app/theme/theme_controller.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// Guards the reason [appThemeProvider] exists: MaterialApp animates a 200 ms
/// whole-app `ThemeData.lerp` whenever the ThemeData it is handed differs from
/// the last one, and two ThemeData built from identical inputs *do* differ.
/// Building the theme inside `ManhwaManiacsApp.build` therefore animated the
/// entire tree on every unrelated root rebuild.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<ProviderContainer> makeContainer() async {
    SharedPreferences.setMockInitialValues(testPrefsDefaults());
    final prefs = await SharedPreferences.getInstance();
    final container = ProviderContainer(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        authenticatedAuthOverride(), // user id 1
        activeProfileOverride(), // profile id 1
      ],
    );
    addTearDown(container.dispose);
    return container;
  }

  test('two fromPalette calls with identical inputs are not ==', () {
    final a = AppTheme.fromPalette(
      AppPalettes.eclipse,
      metrics: AppPresets.signature,
    );
    final b = AppTheme.fromPalette(
      AppPalettes.eclipse,
      metrics: AppPresets.signature,
    );

    expect(
      a == b,
      isFalse,
      reason: 'Several sub-themes are built from '
          'WidgetStateProperty.resolveWith, whose result compares by identity. '
          'If this ever starts passing, appThemeProvider is no longer load '
          'bearing and the hoist can be reconsidered.',
    );
  });

  test('hands back one ThemeData instance while the appearance is unchanged',
      () async {
    final container = await makeContainer();

    expect(
      container.read(appThemeProvider),
      same(container.read(appThemeProvider)),
    );
  });

  test('survives an unrelated rebuild of the palette controller', () async {
    final container = await makeContainer();
    final before = container.read(appThemeProvider);

    // Stands in for the auth/profile transitions that recompute
    // ThemeController.build() without the chosen palette actually changing —
    // the moments that used to restart the 200 ms app-wide lerp. Read the
    // palette back first so the rebuild has definitely happened before the
    // theme is checked.
    container.invalidate(themeControllerProvider);
    expect(
      container.read(themeControllerProvider),
      same(before.extension<AppPalette>()),
    );

    expect(container.read(appThemeProvider), same(before));
  });

  test('a real palette change does produce a new theme', () async {
    final container = await makeContainer();
    final before = container.read(appThemeProvider);

    await container.read(themeControllerProvider.notifier).setTheme('nord');
    final after = container.read(appThemeProvider);

    expect(after, isNot(same(before)));
    expect(after.extension<AppPalette>(), same(Base16Palettes.nord));
    expect(after.scaffoldBackgroundColor, Base16Palettes.nord.bg);
  });
}
