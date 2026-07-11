/// Whether a database restore is staged, waiting for the backend to restart.
///
/// Mirrors the backend's `GET/DELETE /backup/*` payload shape exactly.
class BackupStatus {
  const BackupStatus({required this.restorePending});

  final bool restorePending;

  factory BackupStatus.fromJson(Map<String, dynamic> json) {
    return BackupStatus(
      restorePending: json['restore_pending'] as bool? ?? false,
    );
  }
}
