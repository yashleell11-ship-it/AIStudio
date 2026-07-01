import 'package:aistudio_mobile/features/library/models/statistics_detail.dart';

class LibraryStatistics {
  const LibraryStatistics({
    required this.totalSeries,
    required this.totalChapters,
    required this.totalPages,
    required this.completedSeries,
    required this.inProgress,
    required this.favorites,
    required this.completionRatePct,
    required this.totalReadingTimeEstimateMinutes,
    required this.pagesReadThisWeek,
    required this.readingStreakDays,
    required this.readingVelocityPagesPerHour,
    this.tagDistribution = const [],
    this.topAuthors = const [],
    this.weeklyChart = const [],
  });

  final int totalSeries;
  final int totalChapters;
  final int totalPages;
  final int completedSeries;
  final int inProgress;
  final int favorites;
  final double completionRatePct;
  final int totalReadingTimeEstimateMinutes;
  final int pagesReadThisWeek;
  final int readingStreakDays;
  final double readingVelocityPagesPerHour;
  final List<TagDistributionItem> tagDistribution;
  final List<AuthorStat> topAuthors;
  final List<WeeklyChartItem> weeklyChart;

  factory LibraryStatistics.fromJson(Map<String, dynamic> json) => LibraryStatistics(
        totalSeries: json['total_series'] as int,
        totalChapters: json['total_chapters'] as int,
        totalPages: json['total_pages'] as int,
        completedSeries: json['completed_series'] as int,
        inProgress: json['in_progress'] as int,
        favorites: json['favorites'] as int,
        completionRatePct: (json['completion_rate_pct'] as num).toDouble(),
        totalReadingTimeEstimateMinutes:
            json['total_reading_time_estimate_minutes'] as int,
        pagesReadThisWeek: json['pages_read_this_week'] as int,
        readingStreakDays: json['reading_streak_days'] as int,
        readingVelocityPagesPerHour:
            (json['reading_velocity_pages_per_hour'] as num).toDouble(),
        tagDistribution: (json['tag_distribution'] as List<dynamic>?)
                ?.map((item) => TagDistributionItem.fromJson(item as Map<String, dynamic>))
                .toList() ??
            const [],
        topAuthors: (json['top_authors'] as List<dynamic>?)
                ?.map((item) => AuthorStat.fromJson(item as Map<String, dynamic>))
                .toList() ??
            const [],
        weeklyChart: (json['weekly_chart'] as List<dynamic>?)
                ?.map((item) => WeeklyChartItem.fromJson(item as Map<String, dynamic>))
                .toList() ??
            const [],
      );
}
