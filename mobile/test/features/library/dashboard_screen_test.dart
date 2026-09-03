import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/screens/dashboard_screen.dart';
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

FollowedSeries _followed({
  required int id,
  required String title,
  String sourceId = 'asurascans',
  String seriesKey = 'solo-leveling',
  int chapterCount = 120,
  String coverUrl = '',
}) {
  return FollowedSeries(
    id: id,
    sourceId: sourceId,
    seriesKey: seriesKey,
    title: title,
    coverUrl: coverUrl,
    isFavorite: false,
    readingStatus: 'unread',
    notify: true,
    sortOrder: 0,
    contentRating: 'safe',
    rating: 'safe',
    chapterCount: chapterCount,
  );
}

UpdateNotification _notification({
  required int id,
  required int followedSeriesId,
  String sourceId = 'asurascans',
  String seriesKey = 'solo-leveling',
  double? chapterNumber,
  String chapterTitle = 'Chapter 121',
  bool isRead = false,
}) {
  return UpdateNotification(
    id: id,
    followedSeriesId: followedSeriesId,
    sourceId: sourceId,
    seriesKey: seriesKey,
    chapterKey: 'ch-$id',
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

/// Routed variant: the Library tab plus a stub source-detail destination, so
/// a card tap can be asserted to land on the right route with the right
/// (decoded) parameters.
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
            followed: [
              _followed(id: 1, title: 'Solo Leveling'),
              _followed(id: 2, title: 'Tower of God', seriesKey: 'tower-of-god'),
            ],
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // Every followed series is rendered as a card.
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
            followed: [_followed(id: 1, title: 'Solo Leveling')],
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

    testWidgets('resolves a relative cover URL against the API base',
        (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        await _buildTestApp(
          state: UpdatesState(
            notifications: const [],
            unreadCount: 0,
            followed: [
              _followed(
                id: 1,
                title: 'Omniscient Reader',
                coverUrl: '/sources/asurascans/series/orv/cover',
              ),
            ],
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Omniscient Reader'), findsOneWidget);

      const expectedUrl =
          'http://127.0.0.1:8000/sources/asurascans/series/orv/cover';
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
            followed: [
              // chapterCount is 0 until the backend's first update check
              // runs — the card must stay silent rather than lie.
              _followed(
                id: 1,
                title: "Sword God's Livestream",
                chapterCount: 0,
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
              _notification(id: 1, followedSeriesId: 1, chapterNumber: 120),
              _notification(id: 2, followedSeriesId: 1, chapterNumber: 121),
              // Read notification: counts toward "latest", not toward "new".
              _notification(
                id: 3,
                followedSeriesId: 1,
                chapterNumber: 119,
                isRead: true,
              ),
              // Another series' notification must not leak into this card.
              _notification(id: 4, followedSeriesId: 99, chapterNumber: 400),
            ],
            unreadCount: 3,
            followed: [
              _followed(id: 1, title: 'Solo Leveling', chapterCount: 0),
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
            followed: [
              // The fixture's chapterCount default (120) stands in for a
              // series the update checker has already seeded.
              _followed(id: 1, title: 'Solo Leveling'),
            ],
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('120 chapters'), findsOneWidget);
    });

    testWidgets('tapping a followed series opens its source detail route',
        (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        await _buildRoutedTestApp(
          state: UpdatesState(
            notifications: const [],
            unreadCount: 0,
            followed: [
              _followed(
                id: 1,
                title: 'Solo Leveling',
                sourceId: 'toonily',
                // Slash-bearing keys are real (toonily-family sources); the
                // path builder must encode them so go_router still matches.
                seriesKey: 'series/solo-leveling',
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

    testWidgets('shows empty state when nothing is followed', (tester) async {
      await tester.pumpWidget(
        await _buildTestApp(
          state: const UpdatesState(
            notifications: [],
            unreadCount: 0,
            followed: [],
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
            followed: [],
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
