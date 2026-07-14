import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/screens/dashboard_screen.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/features/updates/models/series_tracker.dart';
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
}) {
  return SeriesTracker(
    id: id,
    source: 'asurascans',
    seriesId: 'solo-leveling',
    seriesTitle: title,
    trackKind: TrackKind.followed,
    localSeriesId: localSeriesId,
    enabled: true,
    notify: true,
    autoDownload: false,
    knownChapterCount: 120,
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
      // The dashboard renders a HomeCoverMarquee (a perpetual ScrollMarquee
      // animation) when there are covers, so pumpAndSettle would never settle.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // Every followed series is rendered as a card — local imports
      // (Solo Leveling, localSeriesId set) AND online-only follows
      // (Tower of God, localSeriesId null but source+seriesId present).
      expect(find.text('Solo Leveling'), findsOneWidget);
      expect(find.text('Tower of God'), findsOneWidget);
      expect(find.text('YOUR MANGA COLLECTION'), findsNothing);
      expect(find.text('Browse'), findsNothing);
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
      // The data branch watches dashboardProvider, which fires a (failing)
      // network request; pump past it so its timer doesn't outlive the test.
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
      // The data branch watches dashboardProvider, which fires a (failing)
      // network request; pump past it so its timer doesn't outlive the test.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Your library is empty'), findsOneWidget);
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
