import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_filter_provider.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_ui_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<ProviderContainer> _container([Map<String, Object> values = const {}]) async {
  SharedPreferences.setMockInitialValues(values);
  final prefs = await SharedPreferences.getInstance();
  return ProviderContainer(
    overrides: [sharedPrefsProvider.overrideWithValue(prefs)],
  );
}

void main() {
  group('ReaderFilter overlay math', () {
    test('full brightness / no warmth produces no overlay', () {
      const filter = ReaderFilter();
      expect(filter.dimAlpha, 0);
      expect(filter.warmthAlpha, 0);
      expect(filter.hasOverlay, isFalse);
    });

    test('lowering brightness dims but never fully blacks out', () {
      const dim = ReaderFilter(brightness: 0.2);
      expect(dim.dimAlpha, greaterThan(0));
      expect(dim.dimAlpha, lessThanOrEqualTo(184));
      expect(dim.hasOverlay, isTrue);
    });

    test('warmth adds an amber overlay', () {
      const warm = ReaderFilter(warmth: 1);
      expect(warm.warmthAlpha, greaterThan(0));
      expect(warm.hasOverlay, isTrue);
    });
  });

  group('ReaderBackground', () {
    test('fromStorageValue falls back to dark for unknown/null', () {
      expect(ReaderBackground.fromStorageValue(null), ReaderBackground.dark);
      expect(ReaderBackground.fromStorageValue('nope'), ReaderBackground.dark);
      expect(ReaderBackground.fromStorageValue('black'), ReaderBackground.black);
    });
  });

  group('readerFilterProvider', () {
    test('defaults to full brightness, no warmth, dark background', () async {
      final container = await _container();
      addTearDown(container.dispose);

      final filter = container.read(readerFilterProvider);
      expect(filter.brightness, 1.0);
      expect(filter.warmth, 0.0);
      expect(filter.background, ReaderBackground.dark);
    });

    test('clamps and persists brightness, warmth and background', () async {
      final container = await _container();
      addTearDown(container.dispose);
      final notifier = container.read(readerFilterProvider.notifier);

      await notifier.setBrightness(0.05); // below floor
      await notifier.setWarmth(0.6);
      await notifier.setBackground(ReaderBackground.black);

      final filter = container.read(readerFilterProvider);
      expect(filter.brightness, 0.2, reason: 'brightness floor is 0.2');
      expect(filter.warmth, 0.6);
      expect(filter.background, ReaderBackground.black);

      final prefs = container.read(preferencesProvider);
      expect(prefs.readerBrightness, 0.2);
      expect(prefs.readerWarmth, 0.6);
      expect(prefs.readerBackground, 'black');
    });

    test('reads persisted values on build', () async {
      final container = await _container({
        'reader_brightness': 0.5,
        'settings_reader_warmth': 0.3,
        'settings_reader_background': 'white',
      });
      addTearDown(container.dispose);

      final filter = container.read(readerFilterProvider);
      expect(filter.brightness, 0.5);
      expect(filter.warmth, 0.3);
      expect(filter.background, ReaderBackground.white);
    });
  });

  group('readerUiProvider double-tap zoom', () {
    test('toggles between 1x and the double-tap level', () async {
      final container = await _container();
      addTearDown(container.dispose);
      final notifier = container.read(readerUiProvider.notifier);

      expect(container.read(readerUiProvider).zoomLevel, 1.0);
      notifier.toggleDoubleTapZoom();
      expect(container.read(readerUiProvider).zoomLevel, doubleTapZoomLevel);
      notifier.toggleDoubleTapZoom();
      expect(container.read(readerUiProvider).zoomLevel, 1.0);
    });
  });
}
