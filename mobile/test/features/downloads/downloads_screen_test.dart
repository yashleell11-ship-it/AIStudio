import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:aistudio_mobile/features/downloads/models/download_metrics.dart';
import 'package:aistudio_mobile/features/downloads/models/download_settings.dart';
import 'package:aistudio_mobile/features/downloads/repositories/downloads_repository.dart';
import 'package:aistudio_mobile/features/downloads/screens/downloads_screen.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class _FakeDownloadsRepository implements DownloadsRepository {
  @override
  Future<Result<List<DownloadItem>>> listDownloads() async => Ok([
        DownloadItem(
          id: 1,
          source: 'test',
          seriesId: 'solo',
          chapterId: 'ch-1',
          seriesTitle: 'Solo Leveling',
          chapterTitle: 'Chapter 1',
          status: 'downloading',
          progress: 45,
          pagesDone: 9,
          pagesTotal: 20,
          bytesDownloaded: 4096000,
          speedBps: 512000,
          speedMbps: 0.5,
          etaSeconds: 22,
          createdAt: DateTime.utc(2024, 1, 1),
          updatedAt: DateTime.utc(2024, 1, 1),
          priority: 0,
          retryCount: 0,
        ),
      ]);

  @override
  Future<Result<DownloadMetrics>> getMetrics() async => Ok(
        DownloadMetrics(
          total: 1,
          completed: 0,
          failed: 0,
          remaining: 1,
          active: 1,
          queued: 0,
          paused: 0,
          storageUsedBytes: 0,
          storageFreeBytes: 0,
          overallSpeedBps: 512000,
          overallSpeedMbps: 0.5,
          overallEtaSeconds: 22,
          workers: const DownloadWorkers(configured: 2, active: 1, running: 1),
        ),
      );

  @override
  Future<Result<DownloadSettings>> getSettings() => throw UnimplementedError();

  @override
  Future<Result<DownloadSettings>> updateSettings(DownloadSettings settings) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> queueChapters({
    required String sourceId,
    required String seriesId,
    required List<String> chapterIds,
    String? seriesTitle,
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
  Future<Result<int>> pauseAll() async => const Ok(1);

  @override
  Future<Result<int>> resumeAll() async => const Ok(1);

  @override
  Future<Result<int>> cancelAll() async => const Ok(1);

  @override
  Future<Result<int>> pauseSeries({
    required String sourceId,
    required String seriesId,
  }) async =>
      const Ok(1);

  @override
  Future<Result<int>> resumeSeries({
    required String sourceId,
    required String seriesId,
  }) async =>
      const Ok(1);

  @override
  Future<Result<int>> cancelSeries({
    required String sourceId,
    required String seriesId,
  }) async =>
      const Ok(1);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DownloadsScreen', () {
    testWidgets('renders active download queue and metrics', (tester) async {
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            downloadsRepositoryProvider.overrideWithValue(_FakeDownloadsRepository()),
          ],
          child: const MaterialApp(home: DownloadsScreen()),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Overall Progress'), findsOneWidget);
      expect(find.text('Solo Leveling'), findsWidgets);
      expect(find.text('Pause All'), findsOneWidget);
      expect(find.textContaining('45%'), findsWidgets);
    });

    testWidgets('shows retry on load failure', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            downloadsRepositoryProvider.overrideWithValue(_FailingDownloadsRepository()),
          ],
          child: const MaterialApp(home: DownloadsScreen()),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Try Again'), findsOneWidget);
    });
  });
}

class _FailingDownloadsRepository implements DownloadsRepository {
  @override
  Future<Result<List<DownloadItem>>> listDownloads() async =>
      Err(UnknownError(message: 'network failure'));

  @override
  Future<Result<DownloadMetrics>> getMetrics() async =>
      Err(UnknownError(message: 'network failure'));

  @override
  Future<Result<DownloadSettings>> getSettings() => throw UnimplementedError();

  @override
  Future<Result<DownloadSettings>> updateSettings(DownloadSettings settings) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> queueChapters({
    required String sourceId,
    required String seriesId,
    required List<String> chapterIds,
    String? seriesTitle,
    int? priority,
  }) =>
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
