enum TrackKind { followed, downloaded }

class SeriesTracker {
  const SeriesTracker({
    required this.id,
    required this.source,
    required this.seriesId,
    required this.seriesTitle,
    required this.trackKind,
    this.localSeriesId,
    required this.enabled,
    required this.notify,
    required this.autoDownload,
    this.checkIntervalMinutes,
    required this.knownChapterCount,
    this.lastCheckedAt,
    this.lastError,
    this.createdAt,
    this.updatedAt,
  });

  final int id;
  final String source;
  final String seriesId;
  final String seriesTitle;
  final TrackKind trackKind;
  final int? localSeriesId;
  final bool enabled;
  final bool notify;
  final bool autoDownload;
  final int? checkIntervalMinutes;
  final int knownChapterCount;
  final DateTime? lastCheckedAt;
  final String? lastError;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  factory SeriesTracker.fromJson(Map<String, dynamic> json) => SeriesTracker(
        id: json['id'] as int,
        source: json['source'] as String,
        seriesId: json['series_id'] as String,
        seriesTitle: json['series_title'] as String,
        trackKind: json['track_kind'] == 'downloaded'
            ? TrackKind.downloaded
            : TrackKind.followed,
        localSeriesId: json['local_series_id'] as int?,
        enabled: json['enabled'] as bool,
        notify: json['notify'] as bool,
        autoDownload: json['auto_download'] as bool,
        checkIntervalMinutes: json['check_interval_minutes'] as int?,
        knownChapterCount: json['known_chapter_count'] as int,
        lastCheckedAt: json['last_checked_at'] != null
            ? DateTime.tryParse(json['last_checked_at'] as String)
            : null,
        lastError: json['last_error'] as String?,
        createdAt: json['created_at'] != null
            ? DateTime.tryParse(json['created_at'] as String)
            : null,
        updatedAt: json['updated_at'] != null
            ? DateTime.tryParse(json['updated_at'] as String)
            : null,
      );
}
