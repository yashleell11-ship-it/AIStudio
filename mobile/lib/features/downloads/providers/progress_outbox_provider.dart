import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// Saves reading progress the offline-safe way: write locally first, flush
/// to the server later. Every call resolves immediately regardless of
/// network state — the reader must never block (or lose a save) on a flaky
/// connection.
///
/// [flush] drains the local outbox via `POST /reader/progress/batch`. Safe
/// to call as often as you like (connectivity regained, app resumed, right
/// after a save) — the server's furthest-wins merge makes a replayed push
/// harmless, so there is no "flushed twice" failure mode to guard against.
class ProgressOutboxController {
  ProgressOutboxController(this.ref);

  final Ref ref;

  /// Writes [push] to the local outbox, then makes a best-effort attempt to
  /// flush immediately (so a save while online still reaches the server
  /// promptly rather than waiting for the next resume/connectivity event).
  /// A no-op with no active scope — there is nowhere to persist it.
  Future<void> save(ProgressPush push) async {
    final store = ref.read(downloadsStoreProvider);
    if (store == null) return;
    await store.enqueueProgress(push);
    await flush();
  }

  /// Drains every pending push for the active scope. Failures leave the
  /// outbox untouched for the next flush attempt — never thrown, so a
  /// caller wiring this to a lifecycle event never needs its own try/catch.
  Future<void> flush() async {
    final store = ref.read(downloadsStoreProvider);
    if (store == null) return;
    final pending = await store.pendingProgressOutbox();
    if (pending.isEmpty) return;

    try {
      final result = await ref
          .read(readerRepositoryProvider)
          .saveProgressBatch([for (final entry in pending) entry.$2]);
      if (result.isOk) {
        await store.clearProgressOutbox([for (final entry in pending) entry.$1]);
      }
    } catch (_) {
      // Offline or a transient server error — the rows stay queued for the
      // next flush trigger (connectivity regained, app resumed).
    }
  }
}

final progressOutboxControllerProvider = Provider<ProgressOutboxController>(
  ProgressOutboxController.new,
  name: 'progressOutboxController',
);
