import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/services/retention_maintenance.dart';

/// The cross-profile maintenance service (read-then-expire sweep, cap
/// eviction) — built on the same shared database/blob-tree singletons as
/// every [DownloadsStore], so its view of "total device bytes" always
/// matches what the stores themselves would report.
final retentionMaintenanceProvider = Provider<RetentionMaintenance>(
  (ref) => RetentionMaintenance(
    database: ref.watch(downloadsDatabaseProvider),
    blobStore: ref.watch(blobStoreProvider),
  ),
  name: 'retentionMaintenance',
);
