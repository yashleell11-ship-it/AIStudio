import 'package:manhwamaniacs/features/library/models/continue_reading_item.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';

class DashboardData {
  const DashboardData({
    required this.recentlyUpdated,
    required this.continueReading,
    required this.stats,
  });

  final List<FollowedSeries> recentlyUpdated;
  final List<ContinueReadingItem> continueReading;
  final LibraryStatistics stats;

  bool get isEmpty =>
      stats.followedTotal == 0 &&
      recentlyUpdated.isEmpty &&
      continueReading.isEmpty;
}
