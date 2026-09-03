import 'package:manhwamaniacs/features/library/models/collection.dart';

enum CollectionSort { name, series, custom }

String collectionSortLabel(CollectionSort sort) {
  switch (sort) {
    case CollectionSort.series:
      return 'Most series';
    case CollectionSort.custom:
      return 'Custom order';
    case CollectionSort.name:
      return 'Name A–Z';
  }
}

String collectionInitials(String name) {
  final words = name.trim().split(RegExp(r'\s+')).where((word) => word.isNotEmpty).toList();
  if (words.isEmpty) return '?';
  if (words.length == 1) return words.first.substring(0, words.first.length.clamp(0, 2)).toUpperCase();
  return '${words[0][0]}${words[1][0]}'.toUpperCase();
}

List<Collection> filterCollections(List<Collection> items, String query) {
  final normalized = query.trim().toLowerCase();
  if (normalized.isEmpty) return items;
  return items
      .where(
        (collection) =>
            collection.name.toLowerCase().contains(normalized) ||
            (collection.description?.toLowerCase().contains(normalized) ?? false),
      )
      .toList();
}

List<Collection> sortCollections(List<Collection> items, CollectionSort sort) {
  final next = [...items];
  switch (sort) {
    case CollectionSort.series:
      next.sort(
        (a, b) => b.seriesCount.compareTo(a.seriesCount) != 0
            ? b.seriesCount.compareTo(a.seriesCount)
            : a.name.compareTo(b.name),
      );
    case CollectionSort.custom:
      next.sort((a, b) => a.sortOrder.compareTo(b.sortOrder));
    case CollectionSort.name:
      next.sort((a, b) => a.name.compareTo(b.name));
  }
  return next;
}
