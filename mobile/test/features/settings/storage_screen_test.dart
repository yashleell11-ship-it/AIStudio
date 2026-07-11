import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/models/download_item.dart';
import 'package:manhwamaniacs/features/downloads/models/download_metrics.dart';
import 'package:manhwamaniacs/features/downloads/repositories/downloads_repository.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/features/settings/screens/storage_screen.dart';
import 'package:manhwamaniacs/features/settings/services/image_cache_service.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

DownloadMetrics _metrics({
  int storageUsedBytes = 2 * 1024 * 1024,
  int storageFreeBytes = 8 * 1024 * 1024,
  int completed = 3,
}) =>
    DownloadMetrics(
      total: completed,
      completed: completed,
      failed: 0,
      remaining: 0,
      active: 0,
      queued: 0,
      paused: 0,
      storageUsedBytes: storageUsedBytes,
      storageFreeBytes: storageFreeBytes,
      overallSpeedBps: 0,
      overallSpeedMbps: 0,
      workers: const DownloadWorkers(configured: 1, active: 0, running: 0),
    );

class _FakeDownloadsRepository implements DownloadsRepository {
  _FakeDownloadsRepository(this.metrics);

  DownloadMetrics metrics;

  @override
  Future<Result<DownloadMetrics>> getMetrics() async => Ok(metrics);

  @override
  Future<Result<List<DownloadItem>>> listDownloads() async => const Ok([]);

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError();
}

class _FakeImageCacheService implements ImageCacheService {
  var clearCallCount = 0;
  var sizeBytes = 2 * 1024 * 1024;

  @override
  Future<int> getCacheSizeBytes() async => sizeBytes;

  @override
  Future<void> clear() async {
    clearCallCount++;
    sizeBytes = 0;
  }
}

Future<ProviderContainer> _pumpStorage(
  WidgetTester tester, {
  DownloadMetrics? metrics,
  ImageCacheService? imageCache,
}) async {
  final container = ProviderContainer(
    overrides: [
      downloadsRepositoryProvider
          .overrideWithValue(_FakeDownloadsRepository(metrics ?? _metrics())),
      if (imageCache != null)
        imageCacheServiceProvider.overrideWithValue(imageCache),
    ],
  );
  addTearDown(container.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: StorageScreen()),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
  return container;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('renders downloads, image cache and metadata cache sections',
      (tester) async {
    await _pumpStorage(tester);

    expect(find.text('Storage'), findsOneWidget);
    expect(find.text('Downloaded chapters'), findsOneWidget);
    expect(find.text('Image cache'), findsOneWidget);
    expect(find.text('Metadata cache'), findsOneWidget);
  });

  testWidgets('shows formatted downloads storage used/free and chapter count',
      (tester) async {
    await _pumpStorage(
      tester,
      metrics: _metrics(
        completed: 5,
      ),
    );

    expect(find.text('2.0 MB used'), findsOneWidget);
    expect(find.text('8.0 MB free'), findsOneWidget);
    expect(find.text('5 chapters downloaded'), findsOneWidget);
  });

  testWidgets('formats gigabyte-scale download storage', (tester) async {
    await _pumpStorage(
      tester,
      metrics: _metrics(
        storageUsedBytes: 3 * 1024 * 1024 * 1024,
        storageFreeBytes: 10 * 1024 * 1024 * 1024,
      ),
    );

    expect(find.text('3.00 GB used'), findsOneWidget);
    expect(find.text('10.00 GB free'), findsOneWidget);
  });

  testWidgets('singular chapter count reads "1 chapter downloaded"',
      (tester) async {
    await _pumpStorage(tester, metrics: _metrics(completed: 1));

    expect(find.text('1 chapter downloaded'), findsOneWidget);
  });

  testWidgets('shows formatted image cache usage from the injected service',
      (tester) async {
    await _pumpStorage(tester, imageCache: _FakeImageCacheService());

    expect(find.text('2.0 MB'), findsOneWidget);
  });

  testWidgets('tapping Clear image cache clears it and refreshes the usage',
      (tester) async {
    final fakeCache = _FakeImageCacheService();
    await _pumpStorage(tester, imageCache: fakeCache);

    expect(find.text('2.0 MB'), findsOneWidget);

    await tester.tap(find.text('Clear image cache'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(fakeCache.clearCallCount, 1);
    expect(find.text('Image cache cleared.'), findsOneWidget);
    expect(find.text('0 B'), findsOneWidget);
  });

  testWidgets('tapping Clear metadata cache shows a confirmation',
      (tester) async {
    await _pumpStorage(tester, imageCache: _FakeImageCacheService());

    await tester.ensureVisible(find.text('Clear metadata cache'));
    await tester.pump();
    await tester.tap(find.text('Clear metadata cache'));
    await tester.pumpAndSettle();

    expect(find.text('Metadata cache cleared.'), findsOneWidget);
  });
}
