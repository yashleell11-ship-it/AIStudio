import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/theme/app_theme.dart';

void main() {
  test('fromPalette builds a coherent ThemeData for every palette', () {
    for (final p in AppPalettes.all) {
      final theme = AppTheme.fromPalette(p);
      expect(theme.brightness, p.brightness, reason: p.id);
      expect(theme.scaffoldBackgroundColor, p.bg, reason: p.id);
      expect(theme.colorScheme.primary, p.primary, reason: p.id);
      expect(theme.colorScheme.onPrimary, p.primaryFg, reason: p.id);
      expect(theme.extension<AppPalette>(), same(p), reason: p.id);
    }
  });

  test('AppTheme.dark is whatever the app defaults to', () {
    // The name predates both selectable axes, from when Eclipse was the only
    // look there was, and nothing outside these tests reads it. What it still
    // has to guarantee is that "the app with nothing chosen" has ONE answer:
    // a MaterialApp built without the theme controller must wear the same
    // palette a fresh install does, not a second, older default.
    final theme = AppTheme.dark;
    expect(theme.extension<AppPalette>(), same(AppPalettes.defaultPalette));
    expect(theme.scaffoldBackgroundColor, AppPalettes.defaultPalette.bg);
  });

  test('overlay style follows palette brightness on both platforms', () {
    final dark = AppTheme.overlayStyleFor(AppPalettes.eclipse);
    // Android draws light glyphs over dark chrome; iOS reads the *background*
    // brightness field (dark background → light glyphs).
    expect(dark.statusBarIconBrightness, Brightness.light);
    expect(dark.statusBarBrightness, Brightness.dark);

    final light = AppTheme.overlayStyleFor(AppPalettes.daylight);
    expect(light.statusBarIconBrightness, Brightness.dark);
    expect(light.statusBarBrightness, Brightness.light);
    expect(light.systemNavigationBarIconBrightness, Brightness.dark);
  });

  testWidgets('context.colors resolves the installed palette', (tester) async {
    late AppPalette seen;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.fromPalette(Base16Palettes.nord),
        home: Builder(
          builder: (context) {
            seen = context.colors;
            return const SizedBox.shrink();
          },
        ),
      ),
    );
    expect(seen, same(Base16Palettes.nord));
  });

  testWidgets('context.colors falls back to the default on a bare ThemeData',
      (tester) async {
    // Many widget tests pump plain MaterialApp(theme: ThemeData(...)); the
    // fallback keeps them (and any unthemed embedding) rendering sanely.
    late AppPalette seen;
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData(),
        home: Builder(
          builder: (context) {
            seen = context.colors;
            return const SizedBox.shrink();
          },
        ),
      ),
    );
    expect(seen, same(AppPalettes.defaultPalette));
  });
}
