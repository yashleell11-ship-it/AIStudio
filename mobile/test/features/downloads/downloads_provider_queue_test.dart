import 'package:aistudio_mobile/core/network/network_connectivity.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:aistudio_mobile/features/downloads/models/download_metrics.dart';
import 'package:aistudio_mobile/features/downloads/models/download_settings.dart';
import 'package:aistudio_mobile/features/downloads/models/queue_download_response.dart';
import 'package:aistudio_mobile/features/downloads/providers/downloads_provider.dart';
import 'package:aistudio_mobile/features/downloads/repositories/downloads_repository.dart';
import 'package:aistudio_mobile/features/downloads/utils/download_wifi_guard.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

class _QueueDownloadsRepository implements DownloadsRepository {
  _QueueDownloadsRepository({
    this.chaptersResponse = const QueueDownloadResponse(queued: [1], skipped: []),
    this.seriesResponse = const QueueDownloadResponse(queued: [1, 2], skipped: ['ch-old']),
  });

  QueueDownloadResponse chaptersResponse;
  QueueDownloadResponse seriesResponse;

  List<String>? lastChapterIds;
  String? lastSeriesTitle;
  bool queueSeriesCalled = false;
  int listDownloadsCalls = 0;

  @override
  Future<Result<QueueDownloadResponse>> queueChapters({
    required String sourceId,
    required String seriesId,
    required List<String> chapterIds,
    String? seriesTitle,
    int? priority,
  }) async {
    lastChapterIds = chapterIds;
    lastSeriesTitle = seriesTitle;
    return Ok(chaptersResponse);
  }

  @override
  Future<Result<QueueDownloadResponse>> queueSeries({
    required String sourceId,
    required String seriesId,
    int? priority,
  }) async {
    queueSeriesCalled = true;
    return Ok(seriesResponse);
  }

  @override
  Future<Result<List<DownloadItem>>> listDownloads() async {
    listDownloadsCalls++;
    return const Ok([]);
  }

  @override
  Future<Result<DownloadMetrics>> getMetrics() async => Ok(
        DownloadMetrics(
          total: 0,
          completed: 0,
          failed: 0,
          remaining: 0,
          active: 0,
          queued: 0,
          paused: 0,
          storageUsedBytes: 0,
          storageFreeBytes: 0,
          overallSpeedBps: 0,
          overallSpeedMbps: 0,
          overallEtaSeconds: null,
          workers: const DownloadWorkers(configured: 1, active: 0, running: 0),
        ),
      );

  @override
  Future<Result<DownloadSettings>> getSettings() => throw UnimplementedError();

  @override
  Future<Result<DownloadSettings>> updateSettings(DownloadSettings settings) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> pauseDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<void>> resumeDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<void>> cancelDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<void>> retryDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<int>> pauseAll() => throw UnimplementedError();

  @override
  Future<Result<int>> resumeAll() => throw UnimplementedError();

  @override
  Future<Result<int>> cancelAll() => throw UnimplementedError();

  @override
  Future<Result<int>> pauseSeries({
    required String sourceId,
    required String seriesId,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<int>> resumeSeries({
    required String sourceId,
    required String seriesId,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<int>> cancelSeries({
    required String sourceId,
    required String seriesId,
  }) =>
      throw UnimplementedError();
}

class _AlwaysWifiConnectivity implements NetworkConnectivity {
  @override
  Future<bool> isOnWifi() async => true;
}

Future<ProviderContainer> _queueContainer(_QueueDownloadsRepository repo) async {
  SharedPreferences.setMockInitialValues(testPrefsDefaults());
  final prefs = await SharedPreferences.getInstance();
  return ProviderContainer(
    overrides: [
      sharedPrefsProvider.overrideWithValue(prefs),
      downloadsRepositoryProvider.overrideWithValue(repo),
      networkConnectivityProvider.overrideWithValue(_AlwaysWifiConnectivity()),
    ],
  );
}

void main() {
  group('DownloadsNotifier queue actions', () {
    test('queueChapters returns repository response and refreshes list', () async {
      final repo = _QueueDownloadsRepository(
        chaptersResponse: const QueueDownloadResponse(
          queued: [10, 11],
          skipped: ['ch-old'],
        ),
      );
      final container = await _queueContainer(repo);
      addTearDown(container.dispose);

      await container.read(downloadsProvider.future);
      expect(repo.listDownloadsCalls, 1);

      final result = await container.read(downloadsProvider.notifier).queueChapters(
            sourceId: 'mangadex',
            seriesId: 'manga-1',
            chapterIds: ['manga-1:1', 'manga-1:2'],
            seriesTitle: 'Solo Leveling',
          );

      expect(result.isOk, isTrue);
      expect(result.value.queued, [10, 11]);
      expect(result.value.skipped, ['ch-old']);
      expect(repo.lastChapterIds, ['manga-1:1', 'manga-1:2']);
      expect(repo.lastSeriesTitle, 'Solo Leveling');
      expect(repo.listDownloadsCalls, greaterThan(1));
    });

    test('queueSeries returns repository response and refreshes list', () async {
      final repo = _QueueDownloadsRepository(
        seriesResponse: const QueueDownloadResponse(
          queued: [1, 2, 3],
          skipped: [],
        ),
      );
      final container = await _queueContainer(repo);
      addTearDown(container.dispose);

      await container.read(downloadsProvider.future);

      final result = await container.read(downloadsProvider.notifier).queueSeries(
            sourceId: 'mangadex',
            seriesId: 'manga-1',
          );

      expect(result.isOk, isTrue);
      expect(result.value.queued, [1, 2, 3]);
      expect(repo.queueSeriesCalled, isTrue);
      expect(repo.listDownloadsCalls, greaterThan(1));
    });

    test('queueChapters returns Wi-Fi error when Wi-Fi only is enabled', () async {
      final repo = _QueueDownloadsRepository();
      SharedPreferences.setMockInitialValues(
        testPrefsDefaults({'settings_wifi_only_downloads': true}),
      );
      final prefs = await SharedPreferences.getInstance();
      final container = ProviderContainer(
        overrides: [
          sharedPrefsProvider.overrideWithValue(prefs),
          downloadsRepositoryProvider.overrideWithValue(repo),
          networkConnectivityProvider.overrideWithValue(
            _FakeCellularConnectivity(),
          ),
        ],
      );
      addTearDown(container.dispose);

      await container.read(downloadsProvider.future);

      final result = await container.read(downloadsProvider.notifier).queueChapters(
            sourceId: 'mangadex',
            seriesId: 'manga-1',
            chapterIds: ['manga-1:1'],
          );

      expect(result.isErr, isTrue);
      expect(isWifiRequiredDownloadError(result.error), isTrue);
      expect(repo.lastChapterIds, isNull);
    });
  });
}

class _FakeCellularConnectivity implements NetworkConnectivity {
  @override
  Future<bool> isOnWifi() async => false;
}
