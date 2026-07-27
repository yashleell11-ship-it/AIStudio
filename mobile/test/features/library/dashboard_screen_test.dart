import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/screens/dashboard_screen.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/features/updates/models/series_tracker.dart';
import 'package:manhwamaniacs/features/updates/models/update_notification.dart';
import 'package:manhwamaniacs/features/updates/providers/updates_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../support/test_overrides.dart';

class _FakeUpdatesNotifier extends UpdatesNotifier {
  _FakeUpdatesNotifier(this.initialState);

  final UpdatesState initialState;
  bool shouldFail = false;

  @override
  Future<UpdatesState> build() async {
    if (shouldFail) throw const UnknownError(message: 'network failure');
    return initialState;
  }
}

SeriesTracker _followedTracker({
  required int id,
  required String title,
  int? localSeriesId,
  String seriesId = 'solo-leveling',
  String source = 'asurascans',
  int knownChapterCount = 120,
  String? lastError,
}) {
  return SeriesTracker(
    id: id,
    source: source,
    seriesId: seriesId,
    seriesTitle: title,
    trackKind: TrackKind.followed,
    localSeriesId: localSeriesId,
    enabled: true,
    notify: true,
    autoDownload: false,
    knownChapterCount: knownChapterCount,
    lastError: lastError,
  );
}

UpdateNotification _notification({
  required int id,
  required int trackerId,
  double? chapterNumber,
  String chapterTitle = 'Chapter 121',
  bool isRead = false,
}) {
  return UpdateNotification(
    id: id,
    trackerId: trackerId,
    source: 'asurascans',
    seriesId: 'solo-leveling',
    seriesTitle: 'Solo Leveling',
    chapterId: 'ch-$id',
    chapterTitle: chapterTitle,
    chapterNumber: chapterNumber,
    isRead: isRead,
  );
}

Future<Widget> _buildTestApp({
  required UpdatesState state,
  bool shouldFail = false,
}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final notifier = _FakeUpdatesNotifier(state)..shouldFail = shouldFail;

  return ProviderScope(
    overrides: [
      apiBaseUrlOverride('http://127.0.0.1:8000'),
      sharedPrefsProvider.overrideWithValue(prefs),
      updatesProvider.overrideWith(() => notifier),
    ],
    child: const MaterialApp(
      home: DashboardScreen(),
    ),
  );
}

/// Routed variant: the Library tab plus stub destinations, so a card tap can be
/// asserted to land on the right route with the right (decoded) parameters.
Future<Widget> _buildRoutedTestApp({required UpdatesState state}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final notifier = _FakeUpdatesNotifier(state);

  final router = GoRouter(
    initialLocation: '/library',
    routes: [
      GoRoute(
        path: '/library',
        builder: (_, __) => const DashboardScreen(),
        routes: [
          GoRoute(
            path: ':seriesId',
            builder: (_, state) => Scaffold(
              body: Text('LOCAL ${state.pathParameters['seriesId']}'),
            ),
          ),
        ],
      ),
      GoRoute(
        path: '/sources',
        builder: (_, __) => const Scaffold(body: Text('SOURCES LIST')),
        routes: [
          GoRoute(
            path: ':sourceId/series/:seriesId',
            builder: (_, state) => Scaffold(
              body: Text(
                'DETAIL ${state.pathParameters['sourceId']}'
                '|${state.pathParameters['seriesId']}',
              ),
            ),
          ),
        ],
      ),
    ],
  );

  return ProviderScope(
    overrides: [
      apiBaseUrlOverride('http://127.0.0.1:8000'),
      sharedPrefsProvider.overrideWithValue(prefs),
      updatesProvider.overrideWith(() => notifier),
    ],
    child: MaterialApp.router(routerConfig: router),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DashboardScreen', () {
    testWidgets('renders followed series grid', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        await _buildTestApp(
          state: UpdatesState(
            notifications: const [],
            unreadCount: 0,
            trackers: [
              _followedTracker(id: 1, title: 'Solo Leveling', localSeriesId: 10),
              _followedTracker(id: 2, title: 'Tower of God'),
            ],
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // Every followed series is rendered as a card — local imports
      // (Solo Leveling, localSeriesId set) AND online-only follows
      // (Tower of God, localSeriesId null but source+seriesId present).
      expect(find.text('Solo Leveling'), findsOneWidget);
      expect(find.text('Tower of God'), findsOneWidget);
      expect(find.text('2 series followed'), findsOneWidget);

      // ...and nothing else. The hero block, the cover marquee, the ABOUT
      // marketing card and their duplicate CTAs are gone.
      expect(find.text('YOUR FOLLOWED SERIES, TOGETHER'), findsNothing);
      expect(find.text('ABOUT'), findsNothing);
      expect(find.textContaining('one warm, quiet place'), findsNothing);
      expect(find.text('YOUR MANGA COLLECTION'), findsNothing);
      expect(find.text('Browse'), findsNothing);
    });

    testWidgets('offers exactly one Browse affordance when the grid has items',
        (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        await _buildTestApp(
          state: UpdatesState(
            notifications: const [],
            unreadCount: 0,
            trackers: [_followedTracker(id: 1, title: 'Solo Leveling')],
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // One unobtrusive app-bar action, and no Browse Sources pill anywhere.
      expect(find.byTooltip('Browse Sources'), findsOneWidget);
      expect(find.text('BROWSE SOURCES'), findsNothing);
      expect(find.text('Browse Sources'), findsNothing);
    });

    testWidgets('online-only follow uses a source cover, not the placeholder',
        (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      const baseUrl = 'http://127.0.0.1:8000';
      await tester.pumpWidget(
        await _buildTestApp(
          state: UpdatesState(
            notifications: const [],
            unreadCount: 0,
            trackers: [
              // Online-only follow: no localSeriesId, but source+seriesId set.
              _followedTracker(id: 3, title: 'Omniscient Reader'),
            ],
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // The online-only follow appears in the grid...
      expect(find.text('Omniscient Reader'), findsOneWidget);

      // ...and requests its source cover URL (not the grey book placeholder).
      final expectedUrl =
          sourceSeriesCoverUrl(baseUrl, 'asurascans', 'solo-leveling');
      final covers = tester
          .widgetList<SeriesCoverImage>(find.byType(SeriesCoverImage))
          .map((w) => w.url)
          .toList();
      expect(covers, contains(expectedUrl));
    });

    testWidgets('never claims "0 chapters" for a freshly-followed series',
        (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        await _buildTestApp(
          state: UpdatesState(
            notifications: const [],
            unreadCount: 0,
            trackers: [
              // knownChapterCount is 0 until the backend's first update check
              // runs — the card must stay silent rather than lie.
              _followedTracker(
                id: 1,
                title: "Sword God's Livestream",
                knownChapterCount: 0,
              ),
            ],
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text("Sword God's Livestream"), findsOneWidget);
      expect(find.text('0 chapters'), findsNothing);
      expect(find.textContaining('chapters'), findsNothing);
    });

    testWidgets('surfaces the latest chapter and unread count when known',
        (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        await _buildTestApp(
          state: UpdatesState(
            notifications: [
              _notification(id: 1, trackerId: 1, chapterNumber: 120),
              _notification(id: 2, trackerId: 1, chapterNumber: 121),
              // Read notification: counts toward "latest", not toward "new".
              _notification(id: 3, trackerId: 1, chapterNumber: 119, isRead: true),
              // Another tracker's notification must not leak into this card.
              _notification(id: 4, trackerId: 99, chapterNumber: 400),
            ],
            unreadCount: 3,
            trackers: [
              _followedTracker(id: 1, title: 'Solo Leveling', knownChapterCount: 0),
            ],
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Latest: Chapter 121'), findsOneWidget);
      expect(find.text('2 NEW'), findsOneWidget);
    });

    testWidgets('falls back to the known chapter count once it is populated',
        (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        await _buildTestApp(
          state: UpdatesState(
            notifications: const [],
            unreadCount: 0,
            trackers: [
              // The fixture's knownChapterCount default (120) stands in for a
              // tracker the update checker has already seeded.
              _followedTracker(id: 1, title: 'Solo Leveling'),
            ],
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('120 chapters'), findsOneWidget);
    });

    testWidgets('tapping an online-only follow opens its source detail route',
        (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        await _buildRoutedTestApp(
          state: UpdatesState(
            notifications: const [],
            unreadCount: 0,
            trackers: [
              _followedTracker(
                id: 1,
                title: 'Solo Leveling',
                source: 'toonily',
                // Slash-bearing ids are real (toonily-family sources); the path
                // builder must encode them so go_router still matches.
                seriesId: 'series/solo-leveling',
              ),
            ],
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      await tester.tap(find.text('Solo Leveling'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      expect(find.text('DETAIL toonily|series/solo-leveling'), findsOneWidget);
    });

    testWidgets('tapping a locally-imported follow opens the library detail',
        (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        await _buildRoutedTestApp(
          state: UpdatesState(
            notifications: const [],
            unreadCount: 0,
            trackers: [
              _followedTracker(id: 1, title: 'Solo Leveling', localSeriesId: 42),
            ],
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      await tester.tap(find.text('Solo Leveling'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      expect(find.text('LOCAL 42'), findsOneWidget);
    });

    testWidgets('ignores downloaded-only trackers', (tester) async {
      await tester.pumpWidget(
        await _buildTestApp(
          state: const UpdatesState(
            notifications: [],
            unreadCount: 0,
            trackers: [
              SeriesTracker(
                id: 1,
                source: 'asurascans',
                seriesId: 'cached-only',
                seriesTitle: 'Cached Only',
                trackKind: TrackKind.downloaded,
                enabled: true,
                notify: false,
                autoDownload: false,
                knownChapterCount: 5,
              ),
            ],
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Cached Only'), findsNothing);
      expect(find.text('Your library is empty'), findsOneWidget);
    });

    testWidgets('shows empty state when nothing is followed', (tester) async {
      await tester.pumpWidget(
        await _buildTestApp(
          state: const UpdatesState(
            notifications: [],
            unreadCount: 0,
            trackers: [],
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Your library is empty'), findsOneWidget);
      expect(
        find.text('Follow series from Sources to build your warm little shelf.'),
        findsOneWidget,
      );
      // The empty state owns the single Browse affordance; the app-bar action
      // stays hidden so there is never more than one.
      expect(find.text('BROWSE SOURCES'), findsOneWidget);
      expect(find.byTooltip('Browse Sources'), findsNothing);
    });

    testWidgets('shows error state on failure', (tester) async {
      await tester.pumpWidget(
        await _buildTestApp(
          state: const UpdatesState(
            notifications: [],
            unreadCount: 0,
            trackers: [],
          ),
          shouldFail: true,
        ),
      );
      await tester.pump();

      // Error state now shows an "Oops" HeroHeading + the error's userMessage;
      // the retry control keeps its FilledButton.icon "Try Again" label.
      expect(find.text('Something went wrong — please try again.'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
    });
  });
}
