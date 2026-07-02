import 'package:aistudio_mobile/features/reader/models/reader_page.dart';
import 'package:aistudio_mobile/features/reader/utils/page_layout.dart';
import 'package:aistudio_mobile/features/settings/models/reader_defaults.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('page_layout', () {
    const page = ReaderPage(
      id: '1',
      number: 1,
      imageUrl: '/pages/1.jpg',
      width: 800,
      height: 1200,
    );

    test('estimatePageHeight scales with zoom', () {
      final normal = estimatePageHeight(page, 400, 1);
      final zoomed = estimatePageHeight(page, 400, 2);
      expect(zoomed, greaterThan(normal));
    });

    test('resolveVisiblePage tracks scroll offset', () {
      final pages = List.generate(
        3,
        (index) => ReaderPage(
          id: '${index + 1}',
          number: index + 1,
          imageUrl: '/pages/${index + 1}.jpg',
          width: 800,
          height: 1200,
        ),
      );

      final pageHeight = estimatePageHeight(page, 400, 1);
      expect(
        resolveVisiblePage(pages, pageHeight + 10, 400, 1),
        2,
      );
    });

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
