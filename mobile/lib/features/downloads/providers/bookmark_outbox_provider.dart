import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/store/bookmarks_dao.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// The server's cap on one `POST /reader/bookmarks/batch`
/// (`BOOKMARK_BATCH_MAX_ITEMS`). A flush with more than this to say sends
/// several batches rather than taking one 413 for the lot.
const int kBookmarkBatchMaxItems = 200;

/// Bookmarks, offline-first — the bookmark half of what
/// [ProgressOutboxController] does for reading positions, and deliberately
/// NOT the same merge.
///
/// Progress is a furthest-wins scalar: replaying it is harmless because a
/// stale value simply loses. A bookmark is a user-created **object** with an
/// identity, and replaying a create over a delete would resurrect something
/// the reader deliberately threw away. So every bookmark here carries a
/// client-generated id, a delete writes a tombstone rather than removing a
/// row, and both the device ([DownloadsStoreBookmarks.mergeServerBookmarks])
/// and the server (`services.bookmark_service.decide`) treat that tombstone as
/// terminal.
///
/// Every method resolves regardless of network state. [create] and [remove]
/// write to the device first and only then attempt a push, so bookmarking on
/// a plane is an ordinary success and not a queued hope.
///
/// It holds the [store] and [repository] as plain objects rather than a `Ref`
/// it reads later, and that is not a style choice: a sync started from a
/// screen routinely outlives that screen, and a `ref.read` on the far side of
/// an `await` throws once the provider it belongs to has been disposed. A
/// profile switch rebuilds this controller with the new scope's store, which
/// is the same thing watching would have achieved.
class BookmarkOutboxController {
  const BookmarkOutboxController({
    required this.store,
    required this.repository,
  });

  /// The active `(user, profile)` store, or null outside a session — in which
  /// case there is nowhere to put a bookmark and every method is a no-op.
  final DownloadsStore? store;

  final ReaderRepository repository;

  /// Bookmark [id] at an exact position. Returns the stored bookmark, or null
  /// when there is no active scope to store it in.
  ///
  /// One action, no dialog: everything here is what the reader already knows
  /// about where it is, and [note] is the optional thing added afterwards.
  Future<Bookmark?> create({
    required ChapterIdentity id,
    required BookmarkMedia media,
    required int anchorIndex,
    required double anchorFraction,
    required int anchorTotal,
    String? seriesTitle,
    double? chapterNumber,
    String? snippet,
    String? note,
  }) async {
    final store = this.store;
    if (store == null) return null;
    final now = DateTime.now().toUtc();
    final bookmark = Bookmark(
      clientId: Bookmark.mintClientId(),
      sourceId: id.sourceId,
      seriesKey: id.seriesKey,
      chapterKey: id.chapterKey,
      seriesTitle: seriesTitle,
      chapterNumber: chapterNumber,
      mediaType: media,
      anchorIndex: anchorIndex < 1 ? 1 : anchorIndex,
      anchorFraction: clampBookmarkFraction(anchorFraction),
      anchorTotal: anchorTotal < 0 ? 0 : anchorTotal,
      snippet: snippet,
      note: note,
      createdAt: now,
      updatedAt: now,
    );
    final saved = await store.saveBookmark(bookmark);
    await flush();
    return saved;
  }

  /// Tombstone a bookmark. Returns whether this scope held a live one.
  Future<bool> remove(String clientId) async {
    final store = this.store;
    if (store == null) return false;
    final removed = await store.tombstoneBookmark(clientId);
    if (removed) await flush();
    return removed;
  }

  /// Push every pending op for the active scope, oldest first.
  ///
  /// Never throws — a caller wiring this to a lifecycle event or firing it
  /// from a screen that may be gone by the time it resolves needs no
  /// try/catch of its own. A failure leaves the outbox exactly as it was, for
  /// the next trigger.
  ///
  /// Accepted ops are cleared even when the server *refused* them: a rejected
  /// op is settled, not pending — an upsert against a tombstone can never
  /// become valid — and keeping it would retry it forever.
  Future<void> flush() async {
    final store = this.store;
    if (store == null) return;
    try {
      final pending = await store.pendingBookmarkOutbox();
      if (pending.isEmpty) return;

      for (var start = 0;
          start < pending.length;
          start += kBookmarkBatchMaxItems) {
        final end = start + kBookmarkBatchMaxItems;
        final chunk = pending.sublist(
          start,
          end > pending.length ? pending.length : end,
        );
        final result = await repository.syncBookmarks(
          [for (final entry in chunk) entry.$2],
        );
        // Stop at the first failure rather than skipping ahead: the ops are
        // ordered, and sending a later chunk past a create that never landed
        // would apply a delete to a bookmark the server has not been told
        // about yet.
        if (result.isErr) return;
        for (final entry in result.value.serverIds.entries) {
          await store.adoptServerId(entry.key, entry.value);
        }
        await store.clearBookmarkOutbox([for (final entry in chunk) entry.$1]);
      }
    } catch (_) {
      // Offline, a transient server error, or a store that went away under a
      // profile switch — the rows stay queued for the next flush.
    }
  }

  /// Push, then pull the server's view and fold it in. Returns whether the
  /// pull actually changed any device row, so a caller can skip re-reading a
  /// list the server had nothing new to say about — which is every launch
  /// after the first.
  ///
  /// Pulled WITH tombstones, because that is the only way a delete made on
  /// another device is learned: the alternative — treating a row's absence
  /// from the listing as a delete — would wipe the screen the first time the
  /// response was paged short.
  ///
  /// Push before pull, so this device's own changes are already part of the
  /// server's answer and cannot come back as a stale contradiction.
  Future<bool> sync() async {
    final store = this.store;
    if (store == null) return false;
    await flush();
    try {
      final result = await repository.listBookmarks(
        includeDeleted: true,
        limit: 500,
      );
      if (result.isErr) return false;
      return await store.mergeServerBookmarks(result.value) > 0;
    } catch (_) {
      // The device's own rows are the screen's source of truth; a failed pull
      // costs nothing but the news from other devices.
      return false;
    }
  }
}

final bookmarkOutboxControllerProvider = Provider<BookmarkOutboxController>(
  (ref) => BookmarkOutboxController(
    store: ref.watch(downloadsStoreProvider),
    repository: ref.watch(readerRepositoryProvider),
  ),
  name: 'bookmarkOutboxController',
);
