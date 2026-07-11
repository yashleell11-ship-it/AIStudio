import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/diagnostics/performance_monitor.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_display_mode.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('PerformanceMonitor', () {
    test('starts with an empty snapshot', () {
      final monitor = PerformanceMonitor();
      expect(monitor.snapshot.hasData, isFalse);
      expect(monitor.isRunning, isFalse);
      monitor.dispose();
    });

    test('start/stop toggles running state', () {
      final monitor = PerformanceMonitor();
      monitor.start();
      expect(monitor.isRunning, isTrue);
      monitor.start(); // idempotent
      expect(monitor.isRunning, isTrue);
      monitor.stop();
      expect(monitor.isRunning, isFalse);
      monitor.dispose();
    });

    test('setTargetRefreshRate ignores non-positive values', () {
      final monitor = PerformanceMonitor();
      // Should not throw for zero/negative.
      monitor.setTargetRefreshRate(0);
      monitor.setTargetRefreshRate(-1);
      monitor.setTargetRefreshRate(120);
      monitor.dispose();
    });
  });

  group('DisplayModeInfo', () {
    test('unsupported has sane defaults', () {
      const info = DisplayModeInfo.unsupported;
      expect(info.supported, isFalse);
      expect(info.activeRefreshRate, 0);
      expect(info.maxRefreshRate, 0);
    });

    test('PlatformReaderDisplayMode.describe never throws off-Android',
        () async {
      const mode = PlatformReaderDisplayMode();
      final info = await mode.describe();
      // On the test host (not Android) this reports unsupported.
      expect(info.supported, isFalse);
    });
  });
}
