import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode_controller.dart';
import 'package:manhwamaniacs/features/content_mode/widgets/content_mode_switch.dart';
import 'package:manhwamaniacs/features/novels/providers/novels_gate_provider.dart';
import 'package:manhwamaniacs/features/sources/providers/sources_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// The regression bar, made mechanical: with the novels flag off the app the
/// owner uses daily must be **byte-for-byte** what it is today. Not "the same
/// but with a disabled tab" — the switch must not exist at all.
Future<void> _pump(
  WidgetTester tester, {
  required bool novelsEnabled,
}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        authenticatedAuthOverride(),
        activeProfileOverride(),
        novelsGateProvider.overrideWith((ref) async => novelsEnabled),
        novelsEnabledProvider.overrideWithValue(novelsEnabled),
        // With the gate open the scope builds a source-mode index, which is
        // a real /sources call this test does not want.
        sourcesListProvider.overrideWith((ref) async => const []),
      ],
      child: const MaterialApp(
        home: Scaffold(body: ContentModeSwitch()),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  testWidgets('renders nothing at all when the novels gate is shut',
      (tester) async {
    await _pump(tester, novelsEnabled: false);

    expect(find.text('Manga'), findsNothing);
    expect(find.text('Novels'), findsNothing);
    // Not a hidden pill, not a disabled one — no control.
    expect(find.byType(InkWell), findsNothing);
  });

  testWidgets('offers both modes when the gate is open', (tester) async {
    await _pump(tester, novelsEnabled: true);

    expect(find.text('Manga'), findsOneWidget);
    expect(find.text('Novels'), findsOneWidget);
  });

  testWidgets('starts on manga — what the owner reads daily', (tester) async {
    await _pump(tester, novelsEnabled: true);

    final container = ProviderScope.containerOf(
      tester.element(find.byType(ContentModeSwitch)),
    );
    expect(container.read(contentModeControllerProvider), ContentMode.manga);
  });

  testWidgets('tapping Novels switches the whole app', (tester) async {
    await _pump(tester, novelsEnabled: true);

    await tester.tap(find.text('Novels'));
    await tester.pump();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(ContentModeSwitch)),
    );
    expect(container.read(contentModeControllerProvider), ContentMode.novel);
    expect(container.read(contentModeScopeProvider).isNovel, isTrue);
  });

  testWidgets('tapping the mode already active is a no-op', (tester) async {
    await _pump(tester, novelsEnabled: true);

    await tester.tap(find.text('Manga'));
    await tester.pump();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(ContentModeSwitch)),
    );
    expect(container.read(contentModeControllerProvider), ContentMode.manga);
  });
}
