import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/collections/utils/collection_sorting.dart';
import 'package:manhwamaniacs/features/library/models/collection.dart';

Collection _collection({
  required int id,
  required String name,
  int seriesCount = 0,
  int sortOrder = 0,
  String? description,
}) {
  return Collection(
    id: id,
    name: name,
    description: description,
    seriesCount: seriesCount,
    sortOrder: sortOrder,
  );
}

void main() {
  group('collection sorting and search', () {
    test('filters by name and description', () {
      final items = [
        _collection(id: 1, name: 'Action Picks', description: 'Fast reads'),
        _collection(id: 2, name: 'Slow Burn', description: 'Romance'),
      ];

      expect(filterCollections(items, 'action').length, 1);
      expect(filterCollections(items, 'romance').length, 1);
      expect(filterCollections(items, 'missing'), isEmpty);
    });

    test('sorts by name, series count, and custom order', () {
      final items = [
        _collection(id: 1, name: 'Zeta', seriesCount: 2, sortOrder: 2),
        _collection(id: 2, name: 'Alpha', seriesCount: 5, sortOrder: 0),
        _collection(id: 3, name: 'Beta', seriesCount: 5, sortOrder: 1),
      ];

      expect(
        sortCollections(items, CollectionSort.name).map((item) => item.name).toList(),
        ['Alpha', 'Beta', 'Zeta'],
      );
      expect(
        sortCollections(items, CollectionSort.series).first.name,
        'Alpha',
      );
      expect(
        sortCollections(items, CollectionSort.custom).first.name,
        'Alpha',
      );
    });

    test('derives initials from collection name', () {
      expect(collectionInitials('Solo Leveling'), 'SL');
      expect(collectionInitials('Favorites'), 'FA');
      expect(collectionInitials(''), '?');
    });
  });
}
