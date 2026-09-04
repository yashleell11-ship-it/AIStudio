import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/novels/models/novel_typography.dart';

void main() {
  group('clamping', () {
    test('a persisted value out of range is pulled back in, not honoured', () {
      // These are persisted, so a bad one would follow the reader around.
      expect(clampNovelFontSize(4), kMinNovelFontSize);
      expect(clampNovelFontSize(400), kMaxNovelFontSize);
      expect(clampNovelLineHeight(0.1), kMinNovelLineHeight);
      expect(clampNovelLineHeight(9), kMaxNovelLineHeight);
      expect(clampNovelMeasure(2), kMinNovelMeasure);
      expect(clampNovelMeasure(200), kMaxNovelMeasure);
    });

    test('a non-finite value resolves to the default rather than NaN', () {
      expect(clampNovelFontSize(double.nan), kDefaultNovelFontSize);
      expect(clampNovelLineHeight(double.infinity), kDefaultNovelLineHeight);
      expect(clampNovelMeasure(double.nan), kDefaultNovelMeasure);
    });

    test('line height keeps two decimals so the 0.05 step cannot drift', () {
      var height = kDefaultNovelLineHeight;
      for (var i = 0; i < 6; i++) {
        height = stepNovelLineHeight(height, -1);
      }
      expect(height, 1.45);
      expect(stepNovelLineHeight(1.45, -1), kMinNovelLineHeight);
    });
  });

  group('stepping', () {
    test('stops at the ends instead of running off them', () {
      expect(stepNovelFontSize(kMaxNovelFontSize, 1), kMaxNovelFontSize);
      expect(stepNovelFontSize(kMinNovelFontSize, -1), kMinNovelFontSize);
      expect(stepNovelMeasure(kMaxNovelMeasure, 3), kMaxNovelMeasure);
      expect(stepNovelLineHeight(kMaxNovelLineHeight, 1), kMaxNovelLineHeight);
    });

    test('moves by exactly one step', () {
      expect(stepNovelFontSize(19, 1), 20);
      expect(stepNovelMeasure(68, 1), 70);
      expect(stepNovelLineHeight(1.75, 1), 1.8);
    });
  });

  group('column width', () {
    test('caps at the available width rather than overflowing it', () {
      // A phone in portrait is narrower than even the minimum measure, so the
      // control does nothing there and the column is simply the page.
      expect(
        novelColumnWidth(measure: 88, fontSize: 26, available: 380),
        380,
      );
    });

    test('honours the measure once there is room for it', () {
      final width = novelColumnWidth(measure: 68, fontSize: 19, available: 1200);
      expect(width, closeTo(68 * 19 * kNovelMeasureEmFactor, 0.001));
      expect(width, lessThan(1200));
    });
  });

  group('faces', () {
    test('the serif stack leads with real book faces on both platforms', () {
      final serif = novelFontStack(NovelFontFamily.serif);
      expect(serif.first, 'Iowan Old Style'); // iOS / Apple Books
      expect(serif, contains('Noto Serif')); // Android
      expect(serif.last, 'serif');
    });

    test('sans resolves to the platform UI face without naming one', () {
      expect(novelFontStack(NovelFontFamily.sans), isNot(contains('Georgia')));
      expect(novelFontStack(NovelFontFamily.sans).last, 'sans-serif');
    });

    test('an unknown persisted family reads as serif, the default', () {
      expect(NovelFontFamily.fromWire('sans'), NovelFontFamily.sans);
      expect(NovelFontFamily.fromWire('serif'), NovelFontFamily.serif);
      expect(NovelFontFamily.fromWire('cursive'), NovelFontFamily.serif);
      expect(NovelFontFamily.fromWire(null), NovelFontFamily.serif);
    });
  });

  test('the defaults match the web, value for value', () {
    // A book tuned on one client must read the same on the other.
    expect(kDefaultNovelFontSize, 19);
    expect(kDefaultNovelLineHeight, 1.75);
    expect(kDefaultNovelMeasure, 68);
  });
}
