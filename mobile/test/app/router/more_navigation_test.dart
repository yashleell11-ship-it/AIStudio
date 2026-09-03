import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/app.dart';
import 'package:manhwamaniacs/app/router/app_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/features/more/screens/more_screen.dart';
import 'package:manhwamaniacs/features/settings/providers/app_update_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// Mounts the real app (real router, real route table) and parks it on the
/// More tab.
Future<ProviderContainer> _pumpOnMoreTab(WidgetTester tester) async {
  // Tall enough that the whole More list is laid out — it is a lazy ListView.
  await tester.binding.setSurfaceSize(const Size(600, 2000));
  addTearDown(() => tester.binding.setSurfaceSize(null));

  SharedPreferences.setMockInitialValues(testPrefsDefaults());
  final prefs = await SharedPreferences.getInstance();

  final container = ProviderContainer(
    overrides: [
      apiBaseUrlOverride(Env.defaultApiUrl),
      sharedPrefsProvider.overrideWithValue(prefs),
      authenticatedAuthOverride(),
      activeProfileOverride(),
      ...noDownloadsStoreOverrides(),
      profileSessionReadyOverride(),
      appUpdateProvider.overrideWith((ref) async => null),
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

  container.read(appRouterProvider).go(Routes.more);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));

  expect(find.byType(MoreScreen), findsOneWidget);
  return container;
}

NavigatorState _rootNavigator(WidgetTester tester) =>
    tester.state<NavigatorState>(find.byType(Navigator).first);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // Settings / Storage / Backup / Updates / Collections are top-level routes,
  // siblings of the tab shell rather than children of it. Reaching them with
  // `context.go` collapsed the stack to a single page, so `canPop()` was false
  // — and `CupertinoPageTransitionsBuilder` refuses to install its back-swipe
  // on a route that cannot pop. On an iPhone, with no hardware back button,
  // that left a ~40pt chevron as the only way out of each of them.
  group('More tab pushes its destinations so they can be popped', () {
    testWidgets('the More tab itself is the root of the stack', (tester) async {
      await _pumpOnMoreTab(tester);
      expect(_rootNavigator(tester).canPop(), isFalse);
    });

    for (final label in const ['Settings', 'Storage', 'Backup & Restore']) {
      testWidgets('$label is pushed, not swapped in', (tester) async {
        await _pumpOnMoreTab(tester);

        await tester.tap(find.text(label));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));

        expect(
          _rootNavigator(tester).canPop(),
          isTrue,
          reason: 'a route that cannot pop gets no iOS edge-swipe',
        );
        // The tab shell is still mounted underneath (offstage, because the
        // pushed route is opaque) — that is what gives the gesture something to
        // parallax against. `go` would have torn it out of the tree entirely.
        expect(
          find.byType(MoreScreen, skipOffstage: false),
          findsOneWidget,
        );
        expect(
          find.byType(NavigationBar, skipOffstage: false),
          findsOneWidget,
        );
      });
    }

    testWidgets('and popping lands back on the More tab', (tester) async {
      await _pumpOnMoreTab(tester);

      await tester.tap(find.text('Settings'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(_rootNavigator(tester).canPop(), isTrue);

      _rootNavigator(tester).pop();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byType(MoreScreen), findsOneWidget);
      expect(_rootNavigator(tester).canPop(), isFalse);
    });
  });
}
