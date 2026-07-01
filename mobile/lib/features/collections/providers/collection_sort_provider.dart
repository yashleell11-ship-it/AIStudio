import 'package:aistudio_mobile/features/collections/utils/collection_sorting.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final collectionSortProvider = StateProvider<CollectionSort>(
  (ref) => CollectionSort.name,
  name: 'collectionSort',
);
