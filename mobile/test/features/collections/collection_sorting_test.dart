import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/collections/utils/collection_sorting.dart';
import 'package:manhwamaniacs/features/library/models/collection.dart';

Collection _collection({
  required int id,
  required String name,
  int seriesCount = 0,
  DateTime? updatedAt,
  String? description,
}) {
  final timestamp = updatedAt ?? DateTime(2024, 1, id);
  return Collection(
    id: id,
    name: name,
    description: description,
    seriesCount: seriesCount,
    sortOrder: id,
    createdAt: timestamp,
    updatedAt: timestamp,
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

    test('sorts by name, series count, and updated date', () {
      final items = [
        _collection(id: 1, name: 'Zeta', seriesCount: 2, updatedAt: DateTime(2024)),
        _collection(id: 2, name: 'Alpha', seriesCount: 5, updatedAt: DateTime(2024, 6)),
        _collection(id: 3, name: 'Beta', seriesCount: 5, updatedAt: DateTime(2024, 3)),
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
        sortCollections(items, CollectionSort.updated).first.name,
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
