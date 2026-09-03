import 'package:manhwamaniacs/features/library/models/collection.dart';

/// One series membership row inside a [CollectionDetail] — opaque
/// `(sourceId, seriesKey)` identity, not a followed-series id.
class CollectionSeriesRef {
  const CollectionSeriesRef({
    required this.sourceId,
    required this.seriesKey,
    required this.sortOrder,
  });

  final String sourceId;
  final String seriesKey;
  final int sortOrder;

  factory CollectionSeriesRef.fromJson(Map<String, dynamic> json) =>
      CollectionSeriesRef(
        sourceId: json['source_id'] as String,
        seriesKey: json['series_key'] as String,
        sortOrder: (json['sort_order'] as num?)?.toInt() ?? 0,
      );
}

class CollectionDetail {
  const CollectionDetail({
    required this.id,
    required this.name,
    this.description,
    this.coverUrl,
    required this.seriesCount,
    required this.sortOrder,
    required this.series,
  });

  final int id;
  final String name;
  final String? description;
  final String? coverUrl;
  final int seriesCount;
  final int sortOrder;
  final List<CollectionSeriesRef> series;

  Collection toCollection() => Collection(
        id: id,
        name: name,
        description: description,
        coverUrl: coverUrl,
        seriesCount: seriesCount,
        sortOrder: sortOrder,
      );

  factory CollectionDetail.fromJson(Map<String, dynamic> json) => CollectionDetail(
        id: json['id'] as int,
        name: json['name'] as String,
        description: json['description'] as String?,
        coverUrl: json['cover_url'] as String?,
        seriesCount: (json['series_count'] as num?)?.toInt() ?? 0,
        sortOrder: (json['sort_order'] as num?)?.toInt() ?? 0,
        series: (json['series'] as List<dynamic>? ?? const [])
            .map((e) => CollectionSeriesRef.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
