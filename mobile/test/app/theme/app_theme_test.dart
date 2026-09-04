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

  test('AppTheme.dark is the Eclipse palette (back-compat)', () {
    final theme = AppTheme.dark;
    expect(theme.extension<AppPalette>(), same(AppPalettes.eclipse));
    expect(theme.scaffoldBackgroundColor, const Color(0xFF0A0A0A));
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
        theme: AppTheme.fromPalette(AppPalettes.nord),
        home: Builder(
          builder: (context) {
            seen = context.colors;
            return const SizedBox.shrink();
          },
        ),
      ),
    );
    expect(seen, same(AppPalettes.nord));
  });

  testWidgets('context.colors falls back to Eclipse on a bare ThemeData',
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
    expect(seen, same(AppPalettes.eclipse));
  });
}
