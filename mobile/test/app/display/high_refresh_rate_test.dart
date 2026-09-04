import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/display/high_refresh_rate.dart';
import 'package:manhwamaniacs/core/platform/native_bridge.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _RecordingNativeBridge implements NativeBridge {
  final List<bool> highRefreshRateCalls = <bool>[];

  @override
  Future<void> setHighRefreshRateEnabled(bool enabled) async {
    highRefreshRateCalls.add(enabled);
  }

  @override
  Future<DeviceMemoryInfo?> getDeviceMemoryInfo() async => null;

  @override
  Future<void> setVolumeKeyNavEnabled(bool enabled) async {}

  @override
  Stream<VolumeKeyDirection> get volumeKeyEvents => const Stream.empty();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _RecordingNativeBridge bridge;

  Future<ProviderContainer> makeContainer([
    Map<String, Object> seeded = const {},
  ]) async {
    SharedPreferences.setMockInitialValues(seeded);
    final prefs = await SharedPreferences.getInstance();
    bridge = _RecordingNativeBridge();
    final container = ProviderContainer(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        nativeBridgeProvider.overrideWithValue(bridge),
      ],
    );
    addTearDown(container.dispose);
    return container;
  }

  test('defaults to on — the owner asked for the panel maximum', () async {
    final container = await makeContainer();
    expect(container.read(highRefreshRateProvider), isTrue);
  });

  test('reads a persisted opt-out', () async {
    final container =
        await makeContainer({'settings_high_refresh_rate': false});
    expect(container.read(highRefreshRateProvider), isFalse);
  });

  test('setEnabled applies immediately and persists', () async {
    final container = await makeContainer();
    await container.read(highRefreshRateProvider.notifier).setEnabled(false);

    expect(container.read(highRefreshRateProvider), isFalse);
    expect(
      container.read(sharedPrefsProvider).getBool('settings_high_refresh_rate'),
      isFalse,
    );
  });

  group('highRefreshRateSyncProvider', () {
    // Each read below stands in for the `ref.watch` in ManhwaManiacsApp: a
    // read flushes the dirty element, which is exactly what a root rebuild
    // does after the setting changes.
    test('pushes the current setting to the native window', () async {
      final container = await makeContainer();
      container.read(highRefreshRateSyncProvider);

      expect(bridge.highRefreshRateCalls, [true]);
    });

    test('pushes the opt-out so the window preference is actually cleared',
        () async {
      final container = await makeContainer();
      container.read(highRefreshRateSyncProvider);
      await container.read(highRefreshRateProvider.notifier).setEnabled(false);
      container.read(highRefreshRateSyncProvider);

      // `false` must reach the Activity, not merely stop `true` being sent:
      // a window mode preference stays set until something overwrites it.
      expect(bridge.highRefreshRateCalls, [true, false]);
    });
  });
}
