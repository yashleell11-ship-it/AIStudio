import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_filter_provider.dart';

void main() {
  group('ReaderColorMode', () {
    test('normal has no color filter (zero-cost default)', () {
      expect(ReaderColorMode.normal.colorFilter, isNull);
    });

    test('sepia and grayscale expose a color filter', () {
      expect(ReaderColorMode.sepia.colorFilter, isA<ColorFilter>());
      expect(ReaderColorMode.grayscale.colorFilter, isA<ColorFilter>());
    });

    test('fromStorageValue round-trips every mode', () {
      for (final mode in ReaderColorMode.values) {
        expect(ReaderColorMode.fromStorageValue(mode.name), mode);
      }
    });

    test('fromStorageValue falls back to normal for unknown/null', () {
      expect(ReaderColorMode.fromStorageValue(null), ReaderColorMode.normal);
      expect(
        ReaderColorMode.fromStorageValue('bogus'),
        ReaderColorMode.normal,
      );
    });

    test('every mode has a label', () {
      for (final mode in ReaderColorMode.values) {
        expect(mode.label, isNotEmpty);
      }
    });
  });

  group('ReaderFilter', () {
    test('copyWith preserves colorMode when omitted', () {
      const filter = ReaderFilter(colorMode: ReaderColorMode.sepia);
      final copy = filter.copyWith(brightness: 0.5);
      expect(copy.colorMode, ReaderColorMode.sepia);
      expect(copy.brightness, 0.5);
    });

    test('copyWith updates colorMode', () {
      const filter = ReaderFilter();
      final copy = filter.copyWith(colorMode: ReaderColorMode.grayscale);
      expect(copy.colorMode, ReaderColorMode.grayscale);
    });
  });
}
