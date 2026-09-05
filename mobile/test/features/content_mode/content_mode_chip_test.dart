import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode_controller.dart';
import 'package:manhwamaniacs/features/content_mode/widgets/content_mode_chip.dart';
import 'package:manhwamaniacs/features/content_mode/widgets/content_mode_switch.dart';
import 'package:manhwamaniacs/features/library/providers/bookmarks_provider.dart';
import 'package:manhwamaniacs/features/library/screens/bookmarks_screen.dart';
import 'package:manhwamaniacs/features/novels/providers/novels_gate_provider.dart';
import 'package:manhwamaniacs/features/sources/providers/sources_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// The real controller, not [contentModeOverrides] — these tests are about the
/// round trip (tap the chip, pick a mode, the whole app moves), and pinning
/// the controller would test the chip against a mode nothing can change.
Future<List<Override>> _overrides({required bool novelsEnabled}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  return [
    sharedPrefsProvider.overrideWithValue(prefs),
    authenticatedAuthOverride(),
    activeProfileOverride(),
    novelsGateProvider.overrideWith((ref) async => novelsEnabled),
    novelsEnabledProvider.overrideWithValue(novelsEnabled),
    // With the gate open the scope builds a source-mode index, which is a real
    // /sources call this test does not want.
    sourcesListProvider.overrideWith((ref) async => const []),
  ];
}

/// The chip where it actually lives: an [AppBar] action on a screen the mode
/// filters but does not otherwise mention.
Future<void> _pumpChip(
  WidgetTester tester, {
  required bool novelsEnabled,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: await _overrides(novelsEnabled: novelsEnabled),
      child: MaterialApp(
        home: Scaffold(
          appBar: AppBar(
            title: const Text('Downloads'),
            actions: const [ContentModeChip()],
          ),
          body: const SizedBox.shrink(),
        ),
      ),
    ),
  );
  await tester.pump();
}

/// A Bookmarks screen with nothing on it — the list is not the subject here,
/// the app bar is.
class _EmptyBookmarksNotifier extends BookmarksNotifier {
  @override
  Future<BookmarksState> build() async =>
      const BookmarksState(bookmarks: []);

  @override
  Future<void> refresh() async {}
}

Future<void> _pumpBookmarks(
  WidgetTester tester, {
  required bool novelsEnabled,
}) async {
  final router = GoRouter(
    initialLocation: Routes.bookmarks,
    routes: [
      GoRoute(
        path: Routes.bookmarks,
        builder: (_, __) => const BookmarksScreen(),
      ),
    ],
  );

  final overrides = await _overrides(novelsEnabled: novelsEnabled);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        ...overrides,
        bookmarksProvider.overrideWith(_EmptyBookmarksNotifier.new),
      ],
      child: MaterialApp.router(routerConfig: router),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
}

ContentMode _modeOf(WidgetTester tester) =>
    ProviderScope.containerOf(tester.element(find.byType(ContentModeChip)))
        .read(contentModeControllerProvider);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ContentModeChip', () {
    testWidgets('renders nothing at all when the novels gate is shut',
        (tester) async {
      // Same bar as the switch: a deployment without novels is the app the
      // owner uses today, down to the app-bar furniture.
      await _pumpChip(tester, novelsEnabled: false);

      expect(find.text('Manga'), findsNothing);
      expect(find.byIcon(Icons.expand_more), findsNothing);
    });

    testWidgets('names the mode the screen is being filtered by',
        (tester) async {
      await _pumpChip(tester, novelsEnabled: true);

      expect(find.text('Manga'), findsOneWidget);
      expect(find.byIcon(Icons.expand_more), findsOneWidget);
    });

    testWidgets('opens the one switch rather than a second control',
        (tester) async {
      await _pumpChip(tester, novelsEnabled: true);

      await tester.tap(find.byType(ContentModeChip));
      await tester.pumpAndSettle();

      // The sheet hosts the real widget — there is exactly one implementation
      // of choosing a mode in the app.
      expect(find.byType(ContentModeSwitch), findsOneWidget);
      expect(find.text('Novels'), findsOneWidget);
      // And it says what it is, so it cannot be read as a per-screen filter.
      expect(find.text('Reading mode'), findsOneWidget);
    });

    testWidgets('choosing a mode moves the whole app and closes the sheet',
        (tester) async {
      await _pumpChip(tester, novelsEnabled: true);
      expect(_modeOf(tester), ContentMode.manga);

      await tester.tap(find.byType(ContentModeChip));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Novels'));
      await tester.pumpAndSettle();

      expect(_modeOf(tester), ContentMode.novel);
      // Dismissed, so the screen underneath is seen re-filtering.
      expect(find.byType(ContentModeSwitch), findsNothing);
      // …and the chip now names where the screen actually is.
      expect(find.text('Novels'), findsOneWidget);
    });

    testWidgets('picking the mode already in force keeps the sheet open',
        (tester) async {
      await _pumpChip(tester, novelsEnabled: true);

      await tester.tap(find.byType(ContentModeChip));
      await tester.pumpAndSettle();
      // The switch treats this as a no-op, so nothing changed and there is
      // nothing to close the sheet for — the last match is the sheet's pill,
      // not the chip in the bar behind it.
      await tester.tap(find.text('Manga').last);
      await tester.pumpAndSettle();

      expect(_modeOf(tester), ContentMode.manga);
      expect(find.byType(ContentModeSwitch), findsOneWidget);
    });
  });

  group('Bookmarks reaches the mode it is filtered by', () {
    testWidgets('carries the chip in its app bar', (tester) async {
      // The bug this fixes: Bookmarks is scoped by the mode and used to give
      // no way to change it — the only ways out were the Library tab root and
      // Sources.
      await _pumpBookmarks(tester, novelsEnabled: true);

      expect(find.byType(ContentModeChip), findsOneWidget);
      expect(find.text('Manga'), findsOneWidget);

      await tester.tap(find.byType(ContentModeChip));
      await tester.pumpAndSettle();

      expect(find.byType(ContentModeSwitch), findsOneWidget);
    });

    testWidgets('and shows no mode furniture when novels are off',
        (tester) async {
      await _pumpBookmarks(tester, novelsEnabled: false);

      expect(find.text('Bookmarks'), findsWidgets);
      expect(find.text('Manga'), findsNothing);
      expect(find.byIcon(Icons.expand_more), findsNothing);
    });
  });
}
