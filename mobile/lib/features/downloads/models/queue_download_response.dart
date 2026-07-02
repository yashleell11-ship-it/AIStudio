class QueueDownloadResponse {
  const QueueDownloadResponse({
    required this.queued,
    required this.skipped,
    this.warnings = const [],
  });

  final List<int> queued;
  final List<String> skipped;
  final List<String> warnings;

  factory QueueDownloadResponse.fromJson(Map<String, dynamic> json) =>
      QueueDownloadResponse(
        queued: (json['queued'] as List<dynamic>? ?? [])
            .map((value) => (value as num).toInt())
            .toList(),
        skipped: (json['skipped'] as List<dynamic>? ?? [])
            .map((value) => value.toString())
            .toList(),
        warnings: (json['warnings'] as List<dynamic>? ?? [])
            .map((value) => value.toString())
            .toList(),
      );
}
