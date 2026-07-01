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
    this.coverPath,
    required this.seriesCount,
    required this.sortOrder,
    required this.createdAt,
    required this.updatedAt,
  });

  final int id;
  final String name;
  final String? description;
  final String? coverPath;
  final int seriesCount;
  final int sortOrder;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory Collection.fromJson(Map<String, dynamic> json) => Collection(
        id: json['id'] as int,
        name: json['name'] as String,
        description: json['description'] as String?,
        coverPath: json['cover_path'] as String?,
        seriesCount: json['series_count'] as int,
        sortOrder: json['sort_order'] as int,
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
      );
}
