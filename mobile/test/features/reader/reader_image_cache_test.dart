import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/platform/native_bridge.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_image_cache.dart';

class _FakeNativeBridge implements NativeBridge {
  _FakeNativeBridge([this.memoryInfo]);

  DeviceMemoryInfo? memoryInfo;

  @override
  Future<DeviceMemoryInfo?> getDeviceMemoryInfo() async => memoryInfo;

  @override
  Future<void> setVolumeKeyNavEnabled(bool enabled) async {}

  @override
  Stream<VolumeKeyDirection> get volumeKeyEvents => const Stream.empty();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('readerDecodeWidth', () {
    test('returns null when width is unknown or non-positive', () {
      expect(readerDecodeWidth(null, 3), isNull);
      expect(readerDecodeWidth(0, 3), isNull);
      expect(readerDecodeWidth(-5, 3), isNull);
    });

    test('scales logical width by device pixel ratio', () {
      expect(readerDecodeWidth(400, 3), 1200);
      expect(readerDecodeWidth(360, 2), 720);
    });

    test('guards against a zero/negative dpr', () {
      expect(readerDecodeWidth(400, 0), 400);
    });

    test('caps at a sane maximum bitmap width', () {
      expect(readerDecodeWidth(2000, 4), 2880);
    });
  });

  group('tuneReaderImageCache', () {
    test('raises the cache budget to at least 200 MB and never shrinks it',
        () async {
      final cache = PaintingBinding.instance.imageCache;
      const target = 200 << 20;

      cache.maximumSizeBytes = 50 << 20;
      await tuneReaderImageCache(_FakeNativeBridge());
      expect(cache.maximumSizeBytes, greaterThanOrEqualTo(target));

      // A larger existing budget must be preserved (idempotent, grow-only).
      const larger = 400 << 20;
      cache.maximumSizeBytes = larger;
      await tuneReaderImageCache(_FakeNativeBridge());
      expect(cache.maximumSizeBytes, larger);
    });

    test('falls back to the 384 MB floor when device memory is unavailable',
        () async {
      final cache = PaintingBinding.instance.imageCache;
      cache.maximumSizeBytes = 0;

      await tuneReaderImageCache(_FakeNativeBridge());

      expect(cache.maximumSizeBytes, 384 << 20);
    });

    test('never drops below the 384 MB floor on a low-RAM device', () async {
      final cache = PaintingBinding.instance.imageCache;
      cache.maximumSizeBytes = 0;

      await tuneReaderImageCache(
        _FakeNativeBridge(
          const DeviceMemoryInfo(
            totalBytes: 1 << 30, // 1 GB total -- 8% would be well under 384 MB
            availableBytes: 200 << 20,
            lowMemory: true,
          ),
        ),
      );

      expect(cache.maximumSizeBytes, 384 << 20);
    });

    test('scales up toward the 768 MB ceiling on a high-RAM device', () async {
      final cache = PaintingBinding.instance.imageCache;
      cache.maximumSizeBytes = 0;

      await tuneReaderImageCache(
        _FakeNativeBridge(
          const DeviceMemoryInfo(
            totalBytes: 16 << 30, // 16 GB total -- 8% far exceeds the ceiling
            availableBytes: 8 << 30,
            lowMemory: false,
          ),
        ),
      );

      expect(cache.maximumSizeBytes, 768 << 20);
    });
  });
}
