import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/settings/models/backup_status.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// Whether a database restore is currently staged on the backend.
///
/// Resolves to "nothing pending" rather than an error state when the
/// backend is unreachable, so the Backup screen degrades gracefully offline
/// instead of showing a scary error for what's just a connectivity blip.
final backupStatusProvider = FutureProvider.autoDispose<BackupStatus>((ref) async {
  final repo = ref.watch(backupRepositoryProvider);
  final result = await repo.getStatus();
  return result.fold(
    ok: (status) => status,
    err: (_) => const BackupStatus(restorePending: false),
  );
});
