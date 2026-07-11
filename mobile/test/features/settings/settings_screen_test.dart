import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/storage/secure_storage.dart';
import 'package:manhwamaniacs/core/utils/pagination.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/models/download_settings.dart';
import 'package:manhwamaniacs/features/downloads/repositories/downloads_repository.dart';
import 'package:manhwamaniacs/features/library/models/chapter.dart';
import 'package:manhwamaniacs/features/library/models/collection.dart';
import 'package:manhwamaniacs/features/library/models/collection_detail.dart';
import 'package:manhwamaniacs/features/library/models/continue_reading_item.dart';
import 'package:manhwamaniacs/features/library/models/dashboard_data.dart';
import 'package:manhwamaniacs/features/library/models/library_list_state.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';
import 'package:manhwamaniacs/features/library/models/reading_history_item.dart';
import 'package:manhwamaniacs/features/library/models/reading_progress.dart';
import 'package:manhwamaniacs/features/library/models/series_detail.dart';
import 'package:manhwamaniacs/features/library/models/series_summary.dart';
import 'package:manhwamaniacs/features/library/models/tag.dart';
import 'package:manhwamaniacs/features/library/providers/bookmarks_provider.dart';
import 'package:manhwamaniacs/features/library/providers/dashboard_providers.dart';
import 'package:manhwamaniacs/features/library/providers/intelligence_providers.dart';
import 'package:manhwamaniacs/features/library/providers/library_list_provider.dart';
import 'package:manhwamaniacs/features/library/repositories/library_repository.dart';
import 'package:manhwamaniacs/features/reader/models/adjacent_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/settings/providers/app_update_provider.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/features/settings/screens/settings_screen.dart';
import 'package:manhwamaniacs/features/updates/providers/updates_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../support/test_overrides.dart';

class _FakeSecureStorageService extends SecureStorageService {
  String? _storedUrl;

  @override
  Future<String?> getApiUrl() async => _storedUrl;

  @override
  Future<void> setApiUrl(String url) async {
    _storedUrl = url;
  }

  @override
  Future<void> clearApiUrl() async {
    _storedUrl = null;
  }
}

const _emptyLibraryStatistics = LibraryStatistics(
  totalSeries: 0,
  totalChapters: 0,
  totalPages: 0,
  completedSeries: 0,
  inProgress: 0,
  favorites: 0,
  completionRatePct: 0,
  totalReadingTimeEstimateMinutes: 0,
  pagesReadThisWeek: 0,
  readingStreakDays: 0,
  readingVelocityPagesPerHour: 0,
);

class _EmptyLibraryListNotifier extends LibraryListNotifier {
  @override
  Future<LibraryListState> build() async => const LibraryListState();
}

class _EmptySearchListNotifier extends SearchListNotifier {
  @override
  Future<LibraryListState> build() async => const LibraryListState();
}

class _EmptyBookmarksNotifier extends BookmarksNotifier {
  @override
  Future<BookmarksState> build() async => const BookmarksState(bookmarks: []);
}

class _EmptyUpdatesNotifier extends UpdatesNotifier {
  @override
  Future<UpdatesState> build() async => const UpdatesState(
        notifications: [],
        unreadCount: 0,
        trackers: [],
      );
}

List<Override> _metadataCacheProviderOverrides() => [
      dashboardProvider.overrideWith(
        (ref) async => const DashboardData(
          recentlyUpdated: [],
          continueReading: [],
          stats: _emptyLibraryStatistics,
        ),
      ),
      libraryListProvider.overrideWith(_EmptyLibraryListNotifier.new),
      searchListProvider.overrideWith(_EmptySearchListNotifier.new),
      statisticsProvider.overrideWith((ref) async => _emptyLibraryStatistics),
      recommendationsProvider.overrideWith((ref) async => []),
      readingHistoryProvider.overrideWith(
        (ref) async => const ReadingHistoryData(
          sessions: [],
          calendar: [],
        ),
      ),
      bookmarksProvider.overrideWith(_EmptyBookmarksNotifier.new),
      updatesProvider.overrideWith(_EmptyUpdatesNotifier.new),
    ];

class _EmptyLibraryRepository implements LibraryRepository {
  @override
  Future<Result<PagedResult<SeriesSummary>>> listSeries({
    int page = 1,
    int perPage = 20,
    String? sort,
    String? search,
    String? status,
    String? readingStatus,
    int? collectionId,
    int? tagId,
    bool? isFavorite,
    bool? hasChapters,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<SeriesDetail>> getSeries(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<ChapterDetail>> getChapter(int chapterId) => throw UnimplementedError();

  @override
  Future<Result<List<ContinueReadingItem>>> continueReading({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> recentlyAdded({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> recentlyUpdated({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> recommendations({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> search(String query, {int page = 1}) =>
      throw UnimplementedError();

  @override
  Future<Result<ReadingProgress?>> getProgress(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<ReadingProgress>> saveProgress({
    required int seriesId,
    required int chapterId,
    required int lastPage,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> deleteProgress(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<List<Collection>>> listCollections() => throw UnimplementedError();

  @override
  Future<Result<CollectionDetail>> getCollection(int collectionId) => throw UnimplementedError();

  @override
  Future<Result<Collection>> createCollection({
    required String name,
    String? description,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<Collection>> updateCollection(
    int collectionId, {
    String? name,
    String? description,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> deleteCollection(int collectionId) => throw UnimplementedError();

  @override
  Future<Result<void>> addSeriesToCollection(int collectionId, int seriesId) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> removeSeriesFromCollection(int collectionId, int seriesId) =>
      throw UnimplementedError();

  @override
  Future<Result<List<Tag>>> listTags() => throw UnimplementedError();

  @override
  Future<Result<void>> toggleFavorite(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<LibraryStatistics>> statistics() => throw UnimplementedError();

  @override
  Future<Result<List<ReadingHistoryItem>>> readingHistory({int limit = 50}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<ReadingCalendarDay>>> readingCalendar({int days = 30}) =>
      throw UnimplementedError();

  @override
  Future<Result<Bookmark>> addBookmark({
    required int seriesId,
    required int chapterId,
    required int page,
    String? note,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<List<Bookmark>>> listBookmarks({int limit = 200}) => throw UnimplementedError();

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) => throw UnimplementedError();

  @override
  Future<Result<AdjacentChapter?>> getAdjacentChapter(
    int chapterId, {
    required String direction,
  }) =>
      throw UnimplementedError();
}

class _FakeDownloadsRepository implements DownloadsRepository {
  _FakeDownloadsRepository(this.settings);

  DownloadSettings settings;
  DownloadSettings? saved;

  @override
  Future<Result<DownloadSettings>> getSettings() async => Ok(settings);

  @override
  Future<Result<DownloadSettings>> updateSettings(DownloadSettings newSettings) async {
    saved = newSettings;
    settings = newSettings;
    return Ok(newSettings);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError();
}

DownloadSettings _sampleDownloadSettings() => const DownloadSettings(
      concurrentChapters: 2,
      pageConcurrency: 4,
      retryCount: 3,
      retryDelaySeconds: 5,
      timeoutSeconds: 30,
      activeDownloadCount: 0,
    );

final _testPackageInfo = PackageInfo(
  appName: 'ManhwaManiacs',
  packageName: 'com.manhwamaniacs.app',
  version: '1.0.0',
  buildNumber: '1',
);

Future<ProviderContainer> _pumpSettings(WidgetTester tester) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final container = ProviderContainer(
    overrides: [
      apiBaseUrlOverride('http://127.0.0.1:8000'),
      sharedPrefsProvider.overrideWithValue(prefs),
      libraryRepositoryProvider.overrideWithValue(_EmptyLibraryRepository()),
      downloadsRepositoryProvider
          .overrideWithValue(_FakeDownloadsRepository(_sampleDownloadSettings())),
      // PackageInfo.fromPlatform() hits a real platform channel that isn't
      // mocked in widget tests, so override the provider directly instead
      // of introducing a wrapper interface just for this.
      packageInfoProvider.overrideWith((ref) async => _testPackageInfo),
      // Suppress network call in tests — update check should not hit the server.
      appUpdateProvider.overrideWith((ref) async => null),
      secureStorageProvider.overrideWithValue(_FakeSecureStorageService()),
      ..._metadataCacheProviderOverrides(),
    ],
  );
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: SettingsScreen()),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
  return container;
}

/// The General tab is tall enough that most of its content sits outside the
/// default test viewport's build/cache extent. `ListView` only builds
/// children near the viewport, so `find.text()` won't see anything further
/// down until we scroll to it.
Future<void> _scrollToText(WidgetTester tester, String text) async {
  // TabBarView's own PageView is also a Scrollable, so
  // find.byType(Scrollable).first can resolve to that instead of the
  // visible tab's ListView. Target the Scrollable that the ListView itself
  // renders, not the outer PageView's.
  await tester.scrollUntilVisible(
    find.text(text),
    300,
    scrollable: find
        .descendant(of: find.byType(ListView).first, matching: find.byType(Scrollable))
        .first,
  );
  await tester.pump();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('SettingsScreen navigation', () {
    testWidgets('renders General, Server, and About tabs', (tester) async {
      await _pumpSettings(tester);

      expect(find.text('General'), findsOneWidget);
      expect(find.text('Server'), findsOneWidget);
      expect(find.text('About'), findsOneWidget);
    });

    testWidgets('General tab is shown by default with theme/reader sections',
        (tester) async {
      await _pumpSettings(tester);

      expect(find.text('Theme'), findsOneWidget);
      expect(find.text('Language'), findsOneWidget);

      await _scrollToText(tester, 'Default reader preferences');
      expect(find.text('Default reader preferences'), findsOneWidget);

      await _scrollToText(tester, 'Download preferences');
      expect(find.text('Download preferences'), findsOneWidget);
    });

    testWidgets('tapping the Server tab shows the server URL field', (tester) async {
      await _pumpSettings(tester);

      await tester.tap(find.text('Server'));
      await tester.pumpAndSettle();

      expect(find.text('Server connection'), findsOneWidget);
      expect(find.byType(TextField), findsOneWidget);
    });

    testWidgets('search jumps to the tab a result lives on', (tester) async {
      await _pumpSettings(tester);

      await tester.tap(find.byIcon(Icons.search));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'server connection');
      await tester.pumpAndSettle();

      await tester.tap(find.text('Server connection').first);
      await tester.pumpAndSettle();

      expect(find.byType(TextField), findsOneWidget);
      expect(find.text('Server connection'), findsOneWidget);
    });

    testWidgets('tapping the About tab shows version info and licenses button',
        (tester) async {
      await _pumpSettings(tester);

      await tester.tap(find.text('About'));
      await tester.pumpAndSettle();

      expect(find.text('Version'), findsOneWidget);
      expect(find.text('Build'), findsOneWidget);
      expect(find.text('Open source licenses'), findsOneWidget);
    });
  });

  group('SettingsScreen widgets', () {
    testWidgets('shows a radio option for each ThemeMode', (tester) async {
      await _pumpSettings(tester);

      expect(find.text('System'), findsOneWidget);
      expect(find.text('Light'), findsOneWidget);
      expect(find.text('Dark'), findsOneWidget);
      expect(find.byType(RadioListTile<ThemeMode>), findsNWidgets(3));
    });

    testWidgets('selecting Dark updates the persisted theme preference', (tester) async {
      final container = await _pumpSettings(tester);

      await tester.tap(find.text('Dark'));
      await tester.pump();

      expect(container.read(themeModeProvider), ThemeMode.dark);
      expect(container.read(preferencesProvider).themeMode, ThemeMode.dark);
    });

    testWidgets('toggling Keep screen awake persists the preference', (tester) async {
      final container = await _pumpSettings(tester);

      await _scrollToText(tester, 'Keep screen awake');
      await tester.tap(find.text('Keep screen awake'));
      await tester.pump();

      expect(container.read(readerDefaultsProvider).keepScreenAwake, isTrue);
      expect(container.read(preferencesProvider).keepScreenAwake, isTrue);
    });

    testWidgets('toggling Wi-Fi only persists the preference', (tester) async {
      final container = await _pumpSettings(tester);

      await _scrollToText(tester, 'Wi-Fi only');
      await tester.tap(find.text('Wi-Fi only'));
      await tester.pump();

      expect(container.read(wifiOnlyDownloadsProvider), isTrue);
      expect(container.read(preferencesProvider).wifiOnlyDownloads, isTrue);
    });

    testWidgets('existing download concurrency settings still load and save',
        (tester) async {
      await _pumpSettings(tester);

      await _scrollToText(tester, 'Concurrent chapters');
      expect(find.text('Concurrent chapters'), findsOneWidget);
      expect(find.text('Page concurrency'), findsOneWidget);
      expect(find.text('Retry count'), findsOneWidget);

      await _scrollToText(tester, 'Save download settings');
      await tester.tap(find.text('Save download settings'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Download settings saved.'), findsOneWidget);
    });
  });
}