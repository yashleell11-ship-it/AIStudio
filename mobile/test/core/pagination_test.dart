import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/utils/pagination.dart';

void main() {
  group('PaginationParams', () {
    test('defaults to page 1, perPage 20', () {
      const p = PaginationParams();
      expect(p.page, 1);
      expect(p.perPage, 20);
    });

    test('nextPage increments page', () {
      const p = PaginationParams(page: 2, perPage: 10);
      expect(p.nextPage().page, 3);
      expect(p.nextPage().perPage, 10);
    });

    test('toQueryParams returns correct keys', () {
      const p = PaginationParams(page: 3, perPage: 15);
      final q = p.toQueryParams();
      expect(q['page'], 3);
      expect(q['per_page'], 15);
    });
  });

  group('PagedResult', () {
    test('fromJson parses correctly', () {
      final json = {
        'items': [
          {'id': 1},
          {'id': 2},
        ],
        'total': 50,
        'page': 1,
        'per_page': 20,
        'has_next': true,
      };

      final result = PagedResult.fromJson(
        json,
        (e) => e['id'] as int,
      );

      expect(result.items, [1, 2]);
      expect(result.total, 50);
      expect(result.hasNext, isTrue);
      expect(result.totalPages, 3);
    });

    test('isFirstPage returns true only on page 1', () {
      const r = PagedResult<int>(
        items: [],
        total: 100,
        page: 1,
        perPage: 20,
        hasNext: true,
      );
      expect(r.isFirstPage, isTrue);

      const r2 = PagedResult<int>(
        items: [],
        total: 100,
        page: 2,
        perPage: 20,
        hasNext: true,
      );
      expect(r2.isFirstPage, isFalse);
    });

    test('appendItems concatenates lists', () {
      const r = PagedResult<int>(
        items: [1, 2],
        total: 10,
        page: 1,
        perPage: 2,
        hasNext: true,
      );
      final appended = r.appendItems([3, 4], hasNext: false);
      expect(appended.items, [1, 2, 3, 4]);
      expect(appended.hasNext, isFalse);
    });
  });
}
