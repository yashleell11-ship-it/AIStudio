import 'dart:async';

import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:aistudio_mobile/features/downloads/models/download_metrics.dart';
import 'package:aistudio_mobile/features/downloads/models/download_settings.dart';
import 'package:aistudio_mobile/features/downloads/models/queue_download_response.dart';
import 'package:aistudio_mobile/features/downloads/providers/downloads_provider.dart';
import 'package:aistudio_mobile/features/downloads/repositories/downloads_repository.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class _RefreshRepo implements DownloadsRepository {
  _RefreshRepo(this.items);

  List<DownloadItem> items;
  int listCalls = 0;

  @override
  Future<Result<List<DownloadItem>>> listDownloads() async {
    listCalls++;
    return Ok(items);
  }

  @override
  Future<Result<DownloadMetrics>> getMetrics() async => Ok(
        DownloadMetrics(
          total: items.length,
          completed: items.where((item) => item.isCompleted).length,
          failed: items.where((item) => item.isFailed).length,
          remaining: items.length,
          active: items.where((item) => item.isDownloading).length,
          queued: items.where((item) => item.isQueued).length,
          paused: items.where((item) => item.isPaused).length,
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
  Future<Result<QueueDownloadResponse>> queueChapters({
    required String sourceId,
    required String seriesId,
    required List<String> chapterIds,
    String? seriesTitle,
    int? priority,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<QueueDownloadResponse>> queueSeries({
    required String sourceId,
    required String seriesId,
    int? priority,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> pauseDownload(int downloadId) async => const Ok(null);

  @override
  Future<Result<void>> resumeDownload(int downloadId) async => const Ok(null);

  @override
  Future<Result<void>> cancelDownload(int downloadId) async => const Ok(null);

  @override
  Future<Result<void>> retryDownload(int downloadId) async => const Ok(null);

  @override
  Future<Result<int>> pauseAll() async => const Ok(0);

  @override
  Future<Result<int>> resumeAll() async => const Ok(0);

  @override
  Future<Result<int>> cancelAll() async => const Ok(0);

  @override
  Future<Result<int>> pauseSeries({
    required String sourceId,
    required String seriesId,
  }) async =>
      const Ok(0);

  @override
  Future<Result<int>> resumeSeries({
    required String sourceId,
    required String seriesId,
  }) async =>
      const Ok(0);

  @override
  Future<Result<int>> cancelSeries({
    required String sourceId,
    required String seriesId,
  }) async =>
      const Ok(0);
}

DownloadItem _downloadingItem({double progress = 45}) => DownloadItem(
      id: 1,
      source: 'test',
      seriesId: 'solo',
      chapterId: 'ch-1',
      seriesTitle: 'Solo Leveling',
      chapterTitle: 'Chapter 1',
      status: 'downloading',
      progress: progress,
      pagesDone: 9,
      pagesTotal: 20,
      bytesDownloaded: 4096,
      createdAt: DateTime.utc(2024, 1, 1),
      updatedAt: DateTime.utc(2024, 1, 1),
      priority: 0,
      retryCount: 0,
    );

void main() {
  group('DownloadsNotifier.refresh', () {
    test('keeps existing data visible while reloading', () async {
      final repo = _RefreshRepo([_downloadingItem()]);
      final container = ProviderContainer(
        overrides: [downloadsRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(downloadsProvider.future);
      expect(container.read(downloadsProvider).valueOrNull?.items.first.progress, 45);

      repo.items = [_downloadingItem(progress: 80)];
      await container.read(downloadsProvider.notifier).refresh();

      final state = container.read(downloadsProvider);
      expect(state.isLoading, isFalse);
      expect(state.hasValue, isTrue);
      expect(state.value!.items.first.progress, 80);
      expect(repo.listCalls, greaterThan(1));
    });

    test('does not clear actionPending when action starts during refresh', () async {
      final listGate = Completer<void>();
      final pauseGate = Completer<void>();
      final fetchBlocked = Completer<void>();
      final repo = _DelayedRefreshRepo(
        [_downloadingItem()],
        listGate: listGate,
        pauseGate: pauseGate,
        fetchBlocked: fetchBlocked,
      );
      final container = ProviderContainer(
        overrides: [downloadsRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(downloadsProvider.future);
      expect(container.read(downloadsProvider).requireValue.actionPending, isFalse);

      repo.blockListFetch = true;
      final refreshFuture = container.read(downloadsProvider.notifier).refresh();
      await fetchBlocked.future;

      final pauseFuture = container.read(downloadsProvider.notifier).pauseItem(1);

      expect(container.read(downloadsProvider).requireValue.actionPending, isTrue);

      listGate.complete();
      await refreshFuture;

      expect(container.read(downloadsProvider).requireValue.actionPending, isTrue);

      pauseGate.complete();
      await pauseFuture;

      expect(container.read(downloadsProvider).requireValue.actionPending, isFalse);
    });
  });
}

class _DelayedRefreshRepo extends _RefreshRepo {
  _DelayedRefreshRepo(
    super.items, {
    required this.listGate,
    required this.pauseGate,
    required this.fetchBlocked,
  });

  final Completer<void> listGate;
  final Completer<void> pauseGate;
  final Completer<void> fetchBlocked;
  bool blockListFetch = false;

  @override
  Future<Result<List<DownloadItem>>> listDownloads() async {
    if (blockListFetch) {
      if (!fetchBlocked.isCompleted) {
        fetchBlocked.complete();
      }
      await listGate.future;
    }
    return super.listDownloads();
  }

  @override
  Future<Result<void>> pauseDownload(int downloadId) async {
    await pauseGate.future;
    return const Ok(null);
  }
}
