class TagDistributionItem {
  const TagDistributionItem({
    required this.name,
    required this.category,
    this.color,
    required this.seriesCount,
  });

  final String name;
  final String category;
  final String? color;
  final int seriesCount;

  factory TagDistributionItem.fromJson(Map<String, dynamic> json) => TagDistributionItem(
        name: json['name'] as String,
        category: json['category'] as String,
        color: json['color'] as String?,
        seriesCount: json['series_count'] as int,
      );
}

class AuthorStat {
  const AuthorStat({
    required this.author,
    required this.seriesCount,
    required this.totalPages,
  });

  final String author;
  final int seriesCount;
  final int totalPages;

  factory AuthorStat.fromJson(Map<String, dynamic> json) => AuthorStat(
        author: json['author'] as String,
        seriesCount: json['series_count'] as int,
        totalPages: json['total_pages'] as int,
      );
}

class WeeklyChartItem {
  const WeeklyChartItem({
    required this.day,
    required this.label,
    required this.pagesRead,
  });

  final String day;
  final String label;
  final int pagesRead;

  factory WeeklyChartItem.fromJson(Map<String, dynamic> json) => WeeklyChartItem(
        day: json['day'] as String,
        label: json['label'] as String,
        pagesRead: json['pages_read'] as int,
      );
}
