/// A single released version and its highlights, as served by the backend
/// `/app/changelog` endpoint (the same source the landing page renders).
class ChangelogRelease {
  const ChangelogRelease({
    required this.version,
    required this.build,
    required this.date,
    required this.highlights,
  });

  final String version;
  final int build;
  final String date;
  final List<String> highlights;

  factory ChangelogRelease.fromJson(Map<String, dynamic> json) {
    final rawHighlights = json['highlights'];
    return ChangelogRelease(
      version: (json['version'] as String?)?.trim() ?? '',
      build: (json['build'] as num?)?.toInt() ?? 0,
      date: (json['date'] as String?)?.trim() ?? '',
      highlights: rawHighlights is List
          ? rawHighlights.whereType<String>().toList(growable: false)
          : const [],
    );
  }
}
