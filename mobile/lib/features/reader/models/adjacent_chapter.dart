class AdjacentChapter {
  const AdjacentChapter({
    required this.id,
    required this.seriesId,
    required this.title,
    this.number,
  });

  final int id;
  final int seriesId;
  final String title;
  final double? number;

  factory AdjacentChapter.fromJson(Map<String, dynamic> json) => AdjacentChapter(
        id: json['id'] as int,
        seriesId: json['series_id'] as int,
        title: json['title'] as String,
        number: json['number'] != null ? (json['number'] as num).toDouble() : null,
      );
}
