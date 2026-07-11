import 'package:manhwamaniacs/core/utils/pagination.dart';
import 'package:manhwamaniacs/features/library/models/collection.dart';
import 'package:manhwamaniacs/features/library/models/series_summary.dart';

class CollectionDetail {
  const CollectionDetail({
    required this.id,
    required this.name,
    this.description,
    this.coverPath,
    required this.seriesCount,
    required this.sortOrder,
    required this.createdAt,
    required this.updatedAt,
    required this.series,
  });

  final int id;
  final String name;
  final String? description;
  final String? coverPath;
  final int seriesCount;
  final int sortOrder;
  final DateTime createdAt;
  final DateTime updatedAt;
  final PagedResult<SeriesSummary> series;

  Collection toCollection() => Collection(
        id: id,
        name: name,
        description: description,
        coverPath: coverPath,
        seriesCount: seriesCount,
        sortOrder: sortOrder,
        createdAt: createdAt,
        updatedAt: updatedAt,
      );

  factory CollectionDetail.fromJson(Map<String, dynamic> json) => CollectionDetail(
        id: json['id'] as int,
        name: json['name'] as String,
        description: json['description'] as String?,
        coverPath: json['cover_path'] as String?,
        seriesCount: json['series_count'] as int,
        sortOrder: json['sort_order'] as int,
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
        series: PagedResult.fromJson(
          json['series'] as Map<String, dynamic>,
          SeriesSummary.fromJson,
        ),
      );
}
