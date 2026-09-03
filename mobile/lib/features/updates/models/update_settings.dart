/// `GET`/`PUT /updates/settings` — global update-check settings. No
/// `auto_download_enabled` (removed with the server-side download queue).
class UpdateSettings {
  const UpdateSettings({
    required this.enabled,
    required this.checkIntervalMinutes,
    required this.notifyEnabled,
    required this.checkOnStartup,
    this.lastRunAt,
  });

  final bool enabled;
  final int checkIntervalMinutes;
  final bool notifyEnabled;
  final bool checkOnStartup;
  final DateTime? lastRunAt;

  factory UpdateSettings.fromJson(Map<String, dynamic> json) => UpdateSettings(
        enabled: json['enabled'] as bool,
        checkIntervalMinutes: json['check_interval_minutes'] as int,
        notifyEnabled: json['notify_enabled'] as bool,
        checkOnStartup: json['check_on_startup'] as bool,
        lastRunAt: json['last_run_at'] != null
            ? DateTime.tryParse(json['last_run_at'] as String)
            : null,
      );
}

/// `GET /updates/runs` / `GET /updates/runs/{id}` — one update-check sweep.
class UpdateRun {
  const UpdateRun({
    required this.id,
    required this.trigger,
    required this.status,
    required this.seriesChecked,
    required this.newChaptersFound,
    this.error,
    this.startedAt,
    this.finishedAt,
  });

  final int id;
  final String trigger;
  final String status;
  final int seriesChecked;
  final int newChaptersFound;
  final String? error;
  final DateTime? startedAt;
  final DateTime? finishedAt;

  factory UpdateRun.fromJson(Map<String, dynamic> json) => UpdateRun(
        id: json['id'] as int,
        trigger: json['trigger'] as String,
        status: json['status'] as String,
        seriesChecked: (json['series_checked'] as num?)?.toInt() ?? 0,
        newChaptersFound: (json['new_chapters_found'] as num?)?.toInt() ?? 0,
        error: json['error'] as String?,
        startedAt: json['started_at'] != null
            ? DateTime.tryParse(json['started_at'] as String)
            : null,
        finishedAt: json['finished_at'] != null
            ? DateTime.tryParse(json['finished_at'] as String)
            : null,
      );
}
