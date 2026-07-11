import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/platform/native_bridge.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('PlatformNativeBridge on a non-Android host (the test runner)', () {
    // Matches the established pattern for PlatformReaderDisplayMode /
    // PlatformReaderWakelock: every method degrades to a safe no-op off
    // Android rather than touching a platform channel that isn't there.
    final bridge = PlatformNativeBridge();

    test('getDeviceMemoryInfo returns null', () async {
      expect(await bridge.getDeviceMemoryInfo(), isNull);
    });

    test('setVolumeKeyNavEnabled never throws', () async {
      await bridge.setVolumeKeyNavEnabled(true);
      await bridge.setVolumeKeyNavEnabled(false);
    });

    test('volumeKeyEvents never emits', () async {
      final events = <VolumeKeyDirection>[];
      final sub = bridge.volumeKeyEvents.listen(events.add);
      await Future<void>.delayed(const Duration(milliseconds: 20));
      await sub.cancel();
      expect(events, isEmpty);
    });
  });
}
