import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/collections/utils/collection_sorting.dart';

final collectionSortProvider = StateProvider<CollectionSort>(
  (ref) => CollectionSort.name,
  name: 'collectionSort',
);
