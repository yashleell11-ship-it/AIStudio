/// `GET /library/recommendations` item — a top genre over the followed set
/// (`FollowedSeriesService.recommendations`). Without an external catalog
/// there is nothing to recommend beyond the followed set; the client drives a
/// genre-filtered browse from these.
class RecommendationGenre {
  const RecommendationGenre({required this.genre, required this.weight});

  final String genre;
  final int weight;

  factory RecommendationGenre.fromJson(Map<String, dynamic> json) =>
      RecommendationGenre(
        genre: json['genre'] as String,
        weight: (json['weight'] as num?)?.toInt() ?? 0,
      );
}
