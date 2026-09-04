import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/theme/app_theme.dart';
import 'package:manhwamaniacs/app/theme/theme_controller.dart';
import 'package:manhwamaniacs/features/settings/screens/theme_gallery_screen.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// The gallery is the answer to "the picker now has forty-five entries". These
/// are the three affordances that make that number usable — search, the
/// dark/light cut, and applying without leaving the screen — plus the failure
/// mode a search box adds (a query that matches nothing).
Future<ProviderContainer> _pumpGallery(WidgetTester tester) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final container = ProviderContainer(
    overrides: [sharedPrefsProvider.overrideWithValue(prefs)],
  );
  addTearDown(container.dispose);
  // Wired the way the running app wires it — the MaterialApp's ThemeData is
  // rebuilt from the controller — because half of what this screen promises is
  // that picking a theme repaints the screen you picked it on.
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: Consumer(
        builder: (context, ref, _) => MaterialApp(
          theme: AppTheme.fromPalette(ref.watch(themeControllerProvider)),
          home: const ThemeGalleryScreen(),
        ),
      ),
    ),
  );
  await tester.pump();
  return container;
}

Future<void> _search(WidgetTester tester, String query) async {
  await tester.enterText(find.byKey(const Key('theme-search')), query);
  await tester.pumpAndSettle();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('opens on the default theme, grouped dark then light',
      (tester) async {
    await _pumpGallery(tester);

    // Only DARK is asserted here: the light section sits below thirty dark
    // rows and the gallery builds lazily, so it does not exist until it is
    // scrolled — or filtered — into view. The filter test covers it.
    expect(find.text('DARK'), findsOneWidget);
    // The head of the dark section is the default, and it reads as selected.
    expect(find.byKey(const Key('theme-swatch-eclipse')), findsOneWidget);
    expect(find.text('Eclipse'), findsOneWidget);
  });

  testWidgets('search matches name, blurb and author', (tester) async {
    await _pumpGallery(tester);

    // By name.
    await _search(tester, 'kanagawa');
    expect(find.byKey(const Key('theme-swatch-kanagawa')), findsOneWidget);
    expect(find.byKey(const Key('theme-swatch-eclipse')), findsNothing);

    // By something only the blurb says — the word "Hokusai" appears nowhere in
    // the name of the theme it describes.
    await _search(tester, 'hokusai');
    expect(find.byKey(const Key('theme-swatch-kanagawa')), findsOneWidget);

    // By author, which is how you find a family you know by its maker.
    await _search(tester, 'schoonover');
    expect(find.byKey(const Key('theme-swatch-solarized_dark')), findsOneWidget);
    expect(
      find.byKey(const Key('theme-swatch-solarized_light')),
      findsOneWidget,
    );
  });

  testWidgets('a query that matches nothing says so', (tester) async {
    await _pumpGallery(tester);

    await _search(tester, 'zzzzz');
    expect(find.byKey(const Key('theme-swatch-eclipse')), findsNothing);
    expect(find.textContaining('No theme matches'), findsOneWidget);
  });

  testWidgets('the dark/light filter hides the other half', (tester) async {
    await _pumpGallery(tester);

    await tester.tap(find.byKey(const Key('theme-filter-light')));
    await tester.pumpAndSettle();
    expect(find.text('DARK'), findsNothing);
    expect(find.text('LIGHT'), findsOneWidget);
    expect(find.byKey(const Key('theme-swatch-eclipse')), findsNothing);
    expect(find.byKey(const Key('theme-swatch-daylight')), findsOneWidget);

    await tester.tap(find.byKey(const Key('theme-filter-dark')));
    await tester.pumpAndSettle();
    expect(find.text('LIGHT'), findsNothing);
    expect(find.byKey(const Key('theme-swatch-eclipse')), findsOneWidget);

    await tester.tap(find.byKey(const Key('theme-filter-all')));
    await tester.pumpAndSettle();
    expect(find.text('DARK'), findsOneWidget);
    expect(find.byKey(const Key('theme-swatch-eclipse')), findsOneWidget);
  });

  testWidgets('the filter and the search compose', (tester) async {
    await _pumpGallery(tester);

    // "Gruvbox" spans both variants; asking for the light half must leave only
    // the light one, or the two controls are not really composing.
    await _search(tester, 'gruvbox');
    expect(find.byKey(const Key('theme-swatch-gruvbox')), findsOneWidget);
    expect(
      find.byKey(const Key('theme-swatch-gruvbox_light_medium')),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const Key('theme-filter-light')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('theme-swatch-gruvbox')), findsNothing);
    expect(
      find.byKey(const Key('theme-swatch-gruvbox_light_medium')),
      findsOneWidget,
    );
  });

  testWidgets('tapping applies immediately and persists', (tester) async {
    final container = await _pumpGallery(tester);

    await _search(tester, 'dracula');
    await tester.tap(find.byKey(const Key('theme-swatch-dracula')));
    await tester.pumpAndSettle();

    expect(container.read(themeControllerProvider), Base16Palettes.dracula);
    // No signed-in (user, profile) scope in this pump, so it lands in the
    // device slot — the same fallback the Settings strip uses.
    expect(
      container.read(sharedPrefsProvider).getString('mm.theme.device'),
      'dracula',
    );
    // And the gallery itself is now wearing it: the screen it is picking for
    // is the screen it is drawn on.
    final scaffold = tester.widget<Scaffold>(find.byType(Scaffold));
    expect(scaffold.backgroundColor, Base16Palettes.dracula.bg);
  });

  testWidgets('every registered palette is reachable by name', (tester) async {
    // The gallery builds lazily, so "shows all forty-five" cannot be asserted
    // by counting rows on screen. Searching each name proves the same thing
    // and additionally proves the names are what a reader would type.
    await _pumpGallery(tester);

    for (final palette in AppPalettes.all) {
      await _search(tester, palette.name);
      expect(
        find.byKey(Key('theme-swatch-${palette.id}')),
        findsOneWidget,
        reason: palette.id,
      );
    }
  });
}
