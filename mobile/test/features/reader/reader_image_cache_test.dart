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
  Future<void> setHighRefreshRateEnabled(bool enabled) async {}

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

  group('readerDecodedPageBytes', () {
    test('prices the decode at the requested width', () {
      // manhwanex: a 2500x6157 page asked for at 1080 decodes 1080x2660.
      expect(
        readerDecodedPageBytes(
          decodeWidth: 1080,
          pixelWidth: 2500,
          ratio: 2500 / 6157,
        ),
        1080 * 2660 * 4,
      );
    });

    test('never upscales a source narrower than the request', () {
      // manhwaden: 720 wide at source, so 1080 was never going to happen.
      expect(
        readerDecodedPageBytes(
          decodeWidth: 1080,
          pixelWidth: 720,
          ratio: 720 / 14983,
        ),
        720 * 14983 * 4,
      );
    });

    test('falls back to the source width when nothing constrains the decode',
        () {
      expect(
        readerDecodedPageBytes(
          decodeWidth: null,
          pixelWidth: 800,
          ratio: 800 / 1200,
        ),
        800 * 1200 * 4,
      );
    });

    test('says nothing about a page whose size is unknown or unusable', () {
      expect(
        readerDecodedPageBytes(decodeWidth: 1080, pixelWidth: null, ratio: 0.5),
        isNull,
      );
      expect(
        readerDecodedPageBytes(decodeWidth: 1080, pixelWidth: 800, ratio: null),
        isNull,
      );
      expect(
        readerDecodedPageBytes(decodeWidth: 1080, pixelWidth: 0, ratio: 0.5),
        isNull,
      );
      expect(
        readerDecodedPageBytes(decodeWidth: 1080, pixelWidth: 800, ratio: 0),
        isNull,
      );
    });
  });

  group('readerPrefetchTarget', () {
    // The two ends of the measured corpus, decoded at a phone's ~1080 px.
    const heavyPageBytes = 720 * 14983 * 4; // manhwaden, ~41 MB
    const cheapPageBytes = 811 * 1152 * 4; // mangadex, ~3.6 MB

    int target({
      required int fromIndex,
      required int pageCount,
      required int? Function(int) bytes,
    }) =>
        readerPrefetchTarget(
          fromIndex: fromIndex,
          pageCount: pageCount,
          knownPageBytes: bytes,
        );

    test('a 41 MB-per-page source warms one page ahead', () {
      expect(
        target(fromIndex: 0, pageCount: 40, bytes: (_) => heavyPageBytes),
        2,
      );
    });

    test('a 3.6 MB-per-page source still warms well past the old eight', () {
      final reached =
          target(fromIndex: 0, pageCount: 40, bytes: (_) => cheapPageBytes);

      expect(reached, greaterThan(8));
      expect(reached, readerPrefetchMaxPages);
    });

    test('one measured page is enough to collapse the window around it', () {
      // Only the page on screen has decoded; the rest are charged what it cost.
      expect(
        target(
          fromIndex: 0,
          pageCount: 40,
          bytes: (index) => index == 0 ? heavyPageBytes : null,
        ),
        2,
      );
    });

    test('a cold chapter opens on the assumed cost, not on nothing', () {
      // 24 MB assumed against a 64 MB budget: three pages, then stop.
      expect(target(fromIndex: 0, pageCount: 40, bytes: (_) => null), 3);
    });

    test('always warms a page ahead, however heavy the pages are', () {
      // cucumbermanga's worst page is 128 MB on its own — twice the budget.
      expect(
        target(fromIndex: 0, pageCount: 40, bytes: (_) => 128 << 20),
        readerPrefetchMinPages,
      );
    });

    test('spends the budget from the visible page, wherever it is', () {
      expect(
        target(fromIndex: 20, pageCount: 40, bytes: (_) => heavyPageBytes),
        22,
      );
    });

    test('never runs past the end of the feed', () {
      expect(
        target(fromIndex: 38, pageCount: 40, bytes: (_) => cheapPageBytes),
        40,
      );
      expect(target(fromIndex: 0, pageCount: 0, bytes: (_) => null), 0);
      // An index past the end is clamped rather than throwing: scroll handlers
      // ask this while a feed is being replaced under them.
      expect(
        target(fromIndex: 99, pageCount: 3, bytes: (_) => cheapPageBytes),
        3,
      );
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
