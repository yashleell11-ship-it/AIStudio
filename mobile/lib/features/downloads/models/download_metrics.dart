class DownloadWorkers {
  const DownloadWorkers({
    required this.configured,
    required this.active,
    required this.running,
  });

  final int configured;
  final int active;
  final int running;

  factory DownloadWorkers.fromJson(Map<String, dynamic> json) => DownloadWorkers(
        configured: json['configured'] as int,
        active: json['active'] as int,
        running: json['running'] as int,
      );
}

class DownloadMetrics {
  const DownloadMetrics({
    required this.total,
    required this.completed,
    required this.failed,
    required this.remaining,
    required this.active,
    required this.queued,
    required this.paused,
    required this.storageUsedBytes,
    required this.storageFreeBytes,
    required this.overallSpeedBps,
    required this.overallSpeedMbps,
    this.overallEtaSeconds,
    required this.workers,
  });

  final int total;
  final int completed;
  final int failed;
  final int remaining;
  final int active;
  final int queued;
  final int paused;
  final int storageUsedBytes;
  final int storageFreeBytes;
  final double overallSpeedBps;
  final double overallSpeedMbps;
  final double? overallEtaSeconds;
  final DownloadWorkers workers;

  factory DownloadMetrics.fromJson(Map<String, dynamic> json) => DownloadMetrics(
        total: json['total'] as int,
        completed: json['completed'] as int,
        failed: json['failed'] as int,
        remaining: json['remaining'] as int,
        active: json['active'] as int,
        queued: json['queued'] as int,
        paused: json['paused'] as int,
        storageUsedBytes: json['storage_used_bytes'] as int,
        storageFreeBytes: json['storage_free_bytes'] as int,
        overallSpeedBps: (json['overall_speed_bps'] as num).toDouble(),
        overallSpeedMbps: (json['overall_speed_mbps'] as num).toDouble(),
        overallEtaSeconds: json['overall_eta_seconds'] != null
            ? (json['overall_eta_seconds'] as num).toDouble()
            : null,
        workers: DownloadWorkers.fromJson(json['workers'] as Map<String, dynamic>),
      );
}
