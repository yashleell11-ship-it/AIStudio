import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/utils/page_layout.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';

void main() {
  group('page_layout', () {
    test('resolveInitialScrollTop prefers saved scroll', () {
      expect(
        resolveInitialScrollTop(
          savedScroll: 120,
          initialPage: 5,
          pageCount: 10,
          estimatedOffsetToPage: 80,
        ),
        120,
      );
    });

    test('readerFitModeToBoxFit maps persisted fit modes', () {
      expect(readerFitModeToBoxFit(ReaderFitMode.width), BoxFit.fitWidth);
      expect(readerFitModeToBoxFit(ReaderFitMode.height), BoxFit.fitHeight);
      expect(readerFitModeToBoxFit(ReaderFitMode.screen), BoxFit.contain);
    });

    test('isAtReadingEnd respects horizontal direction', () {
      expect(
        isAtReadingEnd(
          scrollOffset: 900,
          viewport: 100,
          maxScroll: 1000,
          direction: ReadingDirection.leftToRight,
        ),
        isTrue,
      );
      expect(
        isAtReadingEnd(
          scrollOffset: 0,
          viewport: 100,
          maxScroll: 1000,
          direction: ReadingDirection.rightToLeft,
        ),
        isTrue,
      );
    });
  });
}
