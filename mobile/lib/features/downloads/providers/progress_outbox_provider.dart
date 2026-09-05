import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/utils/progress_outbox_batch.dart';
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

  /// The batch size the server is known to accept. Starts at the documented
  /// cap and only ever shrinks, on a 413 that names a smaller one — an
  /// instance field so the next flush inherits it instead of rediscovering
  /// the same refusal.
  int _batchLimit = kProgressBatchMaxItems;

  /// Writes [push] to the local outbox, then makes a best-effort attempt to
  /// flush immediately (so a save while online still reaches the server
  /// promptly rather than waiting for the next resume/connectivity event).
  /// A no-op with no active scope — there is nowhere to persist it.
  ///
  /// The capture time is stamped HERE rather than at send time: this is the
  /// moment the reader was actually on that page, and a push flushed after a
  /// flight has to say so or the server dates a week-old read to now.
  Future<void> save(ProgressPush push) async {
    final store = ref.read(downloadsStoreProvider);
    if (store == null) return;
    await store.enqueueProgress(push.stampedAt(DateTime.now().toUtc()));
    await flush();
  }

  /// Drains every pending push for the active scope. Failures leave the
  /// unsent rows queued for the next flush attempt — never thrown, so a
  /// caller wiring this to a lifecycle event never needs its own try/catch.
  ///
  /// Collapsed per chapter and then chunked, because both bound the same
  /// failure: the server refuses a batch over [kProgressBatchMaxItems] items
  /// with a 413, and one 413 used to wedge the outbox permanently — the whole
  /// queue was posted as one array and cleared only on success, so every
  /// later flush resent the same oversized batch and took the same refusal.
  /// An hour of offline reading is enough rows to get there.
  Future<void> flush() async {
    final store = ref.read(downloadsStoreProvider);
    if (store == null) return;
    final pending = await store.pendingProgressOutbox();
    if (pending.isEmpty) return;

    final repository = ref.read(readerRepositoryProvider);
    try {
      for (final chunk in chunkForBatch(
        collapseProgressOutbox(pending),
        max: _batchLimit,
      )) {
        final result = await repository.saveProgressBatch(
          [for (final group in chunk) group.push],
        );
        if (result.isErr) {
          // A server that has since lowered its cap says so in the refusal.
          // Adopt it now so the NEXT flush fits, rather than resending a batch
          // this one already knows is too big (the download queue renegotiates
          // its manifest windows the same way).
          _batchLimit = _capFromBatchTooLarge(result.error) ?? _batchLimit;
          // Stop at the first failing chunk rather than skipping ahead: the
          // remaining chunks stay queued, and a partial flush that dropped
          // them would lose the positions they carry.
          return;
        }
        await store.clearProgressOutbox([
          for (final group in chunk) ...group.outboxIds,
        ]);
      }
    } catch (_) {
      // Offline or a transient server error — the rows stay queued for the
      // next flush trigger (connectivity regained, app resumed).
    }
  }

  int? _capFromBatchTooLarge(AppError error) {
    if (error is! ApiError || error.code != 'batch_too_large') return null;
    final details = error.details;
    if (details is! Map) return null;
    final cap = details['max_items'];
    return cap is num && cap >= 1 ? cap.toInt() : null;
  }
}

final progressOutboxControllerProvider = Provider<ProgressOutboxController>(
  ProgressOutboxController.new,
  name: 'progressOutboxController',
);
