class CollectionRef {
  const CollectionRef({required this.id, required this.name});

  final int id;
  final String name;

  factory CollectionRef.fromJson(Map<String, dynamic> json) => CollectionRef(
        id: json['id'] as int,
        name: json['name'] as String,
      );
}

class Collection {
  const Collection({
    required this.id,
    required this.name,
    this.description,
    this.coverUrl,
    required this.seriesCount,
    required this.sortOrder,
  });

  final int id;
  final String name;
  final String? description;
  final String? coverUrl;
  final int seriesCount;
  final int sortOrder;

  factory Collection.fromJson(Map<String, dynamic> json) => Collection(
        id: json['id'] as int,
        name: json['name'] as String,
        description: json['description'] as String?,
        coverUrl: json['cover_url'] as String?,
        seriesCount: (json['series_count'] as num?)?.toInt() ?? 0,
        sortOrder: (json['sort_order'] as num?)?.toInt() ?? 0,
      );
}
