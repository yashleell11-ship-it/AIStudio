/// Mirror of `GET`/`PUT /downloads/settings`
/// (backend/routes/downloads.py:39-71, served from
/// `DownloadService.get_download_settings`).
class DownloadSettings {
  const DownloadSettings({
    required this.concurrentChapters,
    required this.pageConcurrency,
    required this.retryCount,
    required this.retryDelaySeconds,
    required this.timeoutSeconds,
    required this.activeDownloadCount,
  });

  /// Chapters downloaded simultaneously across every series. Backend bound:
  /// 1–10 (`_SETTING_BOUNDS`, backend/services/download_service.py:29).
  final int concurrentChapters;

  /// Page fetches in flight *within* one chapter. Backend bound: 1–10.
  final int pageConcurrency;

  /// Backend bound: 0–10.
  final int retryCount;

  /// Seconds. Float on the wire (defaults to `0.75`) — see [DownloadSettings.fromJson].
  final double retryDelaySeconds;

  /// Seconds. Float on the wire (defaults to `30.0`).
  final double timeoutSeconds;

  /// Read-only: how many downloads the worker has running right now.
  final int activeDownloadCount;

  /// Every numeric field is read through `as num` first.
  ///
  /// `download_retry_delay_seconds` and `download_timeout_seconds` are declared
  /// `float` server-side (backend/core/config.py:71-73), so they arrive as
  /// `0.75`/`30.0` and `jsonDecode` hands back a `double`. The previous
  /// `as int` cast therefore threw on *every* response, which is why the whole
  /// download settings section only ever rendered its "Couldn't load…" card.
  factory DownloadSettings.fromJson(Map<String, dynamic> json) =>
      DownloadSettings(
        concurrentChapters: _int(json['download_concurrent_chapters']),
        pageConcurrency: _int(json['download_page_concurrency']),
        retryCount: _int(json['download_retry_count']),
        retryDelaySeconds: _double(json['download_retry_delay_seconds']),
        timeoutSeconds: _double(json['download_timeout_seconds']),
        activeDownloadCount: _int(json['active_download_count']),
      );

  Map<String, dynamic> toUpdateJson() => {
        'download_concurrent_chapters': concurrentChapters,
        'download_page_concurrency': pageConcurrency,
        'download_retry_count': retryCount,
        'download_retry_delay_seconds': retryDelaySeconds,
        'download_timeout_seconds': timeoutSeconds,
      };

  DownloadSettings copyWith({
    int? concurrentChapters,
    int? pageConcurrency,
    int? retryCount,
    double? retryDelaySeconds,
    double? timeoutSeconds,
    int? activeDownloadCount,
  }) =>
      DownloadSettings(
        concurrentChapters: concurrentChapters ?? this.concurrentChapters,
        pageConcurrency: pageConcurrency ?? this.pageConcurrency,
        retryCount: retryCount ?? this.retryCount,
        retryDelaySeconds: retryDelaySeconds ?? this.retryDelaySeconds,
        timeoutSeconds: timeoutSeconds ?? this.timeoutSeconds,
        activeDownloadCount: activeDownloadCount ?? this.activeDownloadCount,
      );

  static int _int(Object? value) => (value as num).toInt();

  static double _double(Object? value) => (value as num).toDouble();
}
