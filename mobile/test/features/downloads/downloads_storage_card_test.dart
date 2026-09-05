import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/download_concurrency.dart';
import 'package:manhwamaniacs/features/downloads/models/series_storage_usage.dart';
import 'package:manhwamaniacs/features/downloads/models/storage_cap.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_storage_providers.dart';
import 'package:manhwamaniacs/features/downloads/providers/storage_settings_provider.dart';
import 'package:manhwamaniacs/features/downloads/widgets/downloads_storage_card.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// This screen's real data plumbing (does "Free up space" actually delete
/// the right rows? does the sweep respect pinned/unread/currently-open?) is
/// covered exhaustively against a real FFI-backed store in
/// `retention_maintenance_test.dart` and `downloads_store_test.dart`.
///
/// Driving that same real store through a `testWidgets` pump turned out to
/// be its own hazard: sqflite_common_ffi's background isolate needs actual
/// event-loop turns to reply, `AutomatedTestWidgetsFlutterBinding`'s
/// FakeAsync zone doesn't supply those on its own, and routing the seeding
/// step through `tester.runAsync` to work around that opened a *second*
/// SQLite connection to the same file that then deadlocked against the one
/// the widget's own providers held ("database has been locked for 10s").
/// So this file tests what a widget test should: the screen's own
/// presentation and interaction logic, wired to `downloadsStorageActionsProvider`
/// and the two data providers via lightweight fakes instead of the real
/// store — no FFI, no zone conflicts, and a `freeUpSpace()` call this file
/// can assert was actually invoked.
class _FakeDownloadsStorageActions implements DownloadsStorageActions {
  _FakeDownloadsStorageActions(this.result);

  @override
  Ref get ref => throw UnimplementedError();

  final int result;
  var freeUpSpaceCalls = 0;

  @override
  Future<int> freeUpSpace() async {
    freeUpSpaceCalls++;
    return result;
  }
}

const _breakdown = [
  SeriesStorageUsage(
    sourceId: 'asura',
    seriesKey: 'solo-leveling',
    seriesTitle: 'Solo Leveling',
    bytes: 5 * 1024 * 1024,
    chapterCount: 3,
    pinnedChapterCount: 0,
  ),
  SeriesStorageUsage(
    sourceId: 'asura',
    seriesKey: 'omniscient-reader',
    seriesTitle: 'Omniscient Reader',
    bytes: 2 * 1024 * 1024,
    chapterCount: 1,
    pinnedChapterCount: 1,
  ),
];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<ProviderContainer> pumpCard(
    WidgetTester tester, {
    List<SeriesStorageUsage> breakdown = _breakdown,
    int totalBytes = 7 * 1024 * 1024,
    DownloadsStorageActions? actions,
    bool withScope = true,
  }) async {
    SharedPreferences.setMockInitialValues(testPrefsDefaults());
    final prefs = await SharedPreferences.getInstance();

    final container = ProviderContainer(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        if (withScope) ...[
          authenticatedAuthOverride(),
          activeProfileOverride(),
        ],
        totalDeviceDownloadBytesProvider.overrideWith((ref) async => totalBytes),
        seriesStorageBreakdownProvider.overrideWith((ref) async => breakdown),
        if (actions != null) downloadsStorageActionsProvider.overrideWithValue(actions),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(
          home: Scaffold(body: SingleChildScrollView(child: DownloadsStorageCard())),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    return container;
  }

  testWidgets('shows real device usage and a per-series breakdown', (tester) async {
    await pumpCard(tester);

    expect(find.text('Downloaded chapters'), findsOneWidget);
    expect(find.text('By series'), findsOneWidget);
    expect(find.textContaining('Solo Leveling'), findsOneWidget);
    expect(find.textContaining('Omniscient Reader'), findsOneWidget);
    // The pinned series' row carries the pin glyph, the unpinned one doesn't.
    expect(find.byIcon(Icons.push_pin), findsOneWidget);
  });

  testWidgets('picking a cap persists it', (tester) async {
    final container = await pumpCard(tester);
    expect(container.read(storageCapProvider), StorageCap.gb10);

    await tester.tap(find.byKey(const Key('storage-cap-gb2')));
    await tester.pump();

    expect(container.read(storageCapProvider), StorageCap.gb2);
  });

  testWidgets('picking a chapter concurrency persists it', (tester) async {
    final container = await pumpCard(tester);
    expect(
      container.read(downloadConcurrencyProvider),
      DownloadConcurrency.two,
      reason: 'the default is one step up from serial, not the maximum',
    );

    await tester.tap(find.byKey(const Key('download-concurrency-three')));
    await tester.pump();

    expect(container.read(downloadConcurrencyProvider),
        DownloadConcurrency.three,);
  });

  testWidgets('says what the tradeoff costs, not just that it is faster',
      (tester) async {
    await pumpCard(tester);

    expect(find.text('Chapters at once'), findsOneWidget);
    // The honest half: the owner's own server, and a source that may refuse.
    expect(find.textContaining('your own server'), findsOneWidget);
    expect(find.textContaining('refusing requests'), findsOneWidget);
  });

  testWidgets('free up space calls through and reports the result', (tester) async {
    final actions = _FakeDownloadsStorageActions(2);
    await pumpCard(tester, actions: actions);

    // The card grew a concurrency section above this button, which puts it
    // past the bottom of the 800x600 test viewport.
    await tester.ensureVisible(find.byKey(const Key('free-up-space')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('free-up-space')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(actions.freeUpSpaceCalls, 1);
    expect(find.text('Removed 2 chapters.'), findsOneWidget);
  });

  testWidgets('free up space with nothing to remove says so', (tester) async {
    final actions = _FakeDownloadsStorageActions(0);
    await pumpCard(tester, actions: actions);

    // The card grew a concurrency section above this button, which puts it
    // past the bottom of the 800x600 test viewport.
    await tester.ensureVisible(find.byKey(const Key('free-up-space')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('free-up-space')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('Nothing to free up right now.'), findsOneWidget);
  });

  testWidgets('renders nothing with no active profile', (tester) async {
    await pumpCard(tester, withScope: false);

    expect(find.text('Downloaded chapters'), findsNothing);
  });
}
