/// `GET /library/statistics` (`FollowedSeriesService.statistics`).
class LibraryStatistics {
  const LibraryStatistics({
    required this.followedTotal,
    required this.favorites,
    required this.byReadingStatus,
    required this.chaptersCompleted,
  });

  final int followedTotal;
  final int favorites;
  final Map<String, int> byReadingStatus;
  final int chaptersCompleted;

  factory LibraryStatistics.fromJson(Map<String, dynamic> json) => LibraryStatistics(
        followedTotal: (json['followed_total'] as num?)?.toInt() ?? 0,
        favorites: (json['favorites'] as num?)?.toInt() ?? 0,
        byReadingStatus: (json['by_reading_status'] as Map<String, dynamic>? ?? const {})
            .map((key, value) => MapEntry(key, (value as num).toInt())),
        chaptersCompleted: (json['chapters_completed'] as num?)?.toInt() ?? 0,
      );
}
