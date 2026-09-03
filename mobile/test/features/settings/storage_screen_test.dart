import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/features/settings/screens/storage_screen.dart';
import 'package:manhwamaniacs/features/settings/services/image_cache_service.dart';

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
  ImageCacheService? imageCache,
}) async {
  final container = ProviderContainer(
    overrides: [
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

  testWidgets('renders image cache and metadata cache sections', (tester) async {
    await _pumpStorage(tester);

    expect(find.text('Storage'), findsOneWidget);
    expect(find.text('Image cache'), findsOneWidget);
    expect(find.text('Metadata cache'), findsOneWidget);
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
