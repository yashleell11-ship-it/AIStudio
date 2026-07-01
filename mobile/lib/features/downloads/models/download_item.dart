class DownloadItem {
  const DownloadItem({
    required this.id,
    required this.source,
    required this.seriesId,
    required this.chapterId,
    required this.seriesTitle,
    required this.chapterTitle,
    required this.status,
    required this.progress,
    required this.pagesDone,
    required this.pagesTotal,
    required this.bytesDownloaded,
    this.speedBps,
    this.speedMbps,
    this.etaSeconds,
    this.localChapterId,
    required this.createdAt,
    required this.updatedAt,
    this.error,
    required this.priority,
    this.queueState,
    required this.retryCount,
  });

  final int id;
  final String source;
  final String seriesId;
  final String chapterId;
  final String seriesTitle;
  final String chapterTitle;
  final String status;
  final double progress;
  final int pagesDone;
  final int pagesTotal;
  final int bytesDownloaded;
  final double? speedBps;
  final double? speedMbps;
  final double? etaSeconds;
  final int? localChapterId;
  final DateTime createdAt;
  final DateTime updatedAt;
  final String? error;
  final int priority;
  final String? queueState;
  final int retryCount;

  bool get isDownloading => status == 'downloading';
  bool get isQueued => status == 'queued';
  bool get isPaused => status == 'paused';
  bool get isFailed => status == 'failed';
  bool get isCompleted => status == 'completed';
  bool get isCancelled => status == 'cancelled';

  factory DownloadItem.fromJson(Map<String, dynamic> json) => DownloadItem(
        id: json['id'] as int,
        source: json['source'] as String,
        seriesId: json['series_id'].toString(),
        chapterId: json['chapter_id'].toString(),
        seriesTitle: json['series_title'] as String,
        chapterTitle: json['chapter_title'] as String,
        status: json['status'] as String,
        progress: (json['progress'] as num).toDouble(),
        pagesDone: json['pages_done'] as int,
        pagesTotal: json['pages_total'] as int,
        bytesDownloaded: json['bytes_downloaded'] as int,
        speedBps: json['speed_bps'] != null ? (json['speed_bps'] as num).toDouble() : null,
        speedMbps: json['speed_mbps'] != null ? (json['speed_mbps'] as num).toDouble() : null,
        etaSeconds: json['eta_seconds'] != null ? (json['eta_seconds'] as num).toDouble() : null,
        localChapterId: json['local_chapter_id'] as int?,
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
        error: json['error'] as String?,
        priority: json['priority'] as int,
        queueState: json['queue_state'] as String?,
        retryCount: json['retry_count'] as int,
      );
}
