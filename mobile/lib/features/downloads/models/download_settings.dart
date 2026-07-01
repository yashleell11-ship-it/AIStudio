class DownloadSettings {
  const DownloadSettings({
    required this.concurrentChapters,
    required this.pageConcurrency,
    required this.retryCount,
    required this.retryDelaySeconds,
    required this.timeoutSeconds,
    required this.activeDownloadCount,
  });

  final int concurrentChapters;
  final int pageConcurrency;
  final int retryCount;
  final int retryDelaySeconds;
  final int timeoutSeconds;
  final int activeDownloadCount;

  factory DownloadSettings.fromJson(Map<String, dynamic> json) => DownloadSettings(
        concurrentChapters: json['download_concurrent_chapters'] as int,
        pageConcurrency: json['download_page_concurrency'] as int,
        retryCount: json['download_retry_count'] as int,
        retryDelaySeconds: json['download_retry_delay_seconds'] as int,
        timeoutSeconds: json['download_timeout_seconds'] as int,
        activeDownloadCount: json['active_download_count'] as int,
      );

  Map<String, dynamic> toUpdateJson() => {
        'download_concurrent_chapters': concurrentChapters,
        'download_page_concurrency': pageConcurrency,
        'download_retry_count': retryCount,
        'download_retry_delay_seconds': retryDelaySeconds,
        'download_timeout_seconds': timeoutSeconds,
      };
}
