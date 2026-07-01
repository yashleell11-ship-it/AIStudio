import 'package:aistudio_mobile/features/library/models/chapter.dart';
import 'package:aistudio_mobile/features/reader/utils/page_layout.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('page_layout', () {
    const page = PageInfo(
      id: 1,
      chapterId: 10,
      number: 1,
      filePath: '/pages/1.jpg',
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
        (index) => PageInfo(
          id: index + 1,
          chapterId: 10,
          number: index + 1,
          filePath: '/pages/${index + 1}.jpg',
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
  });
}
