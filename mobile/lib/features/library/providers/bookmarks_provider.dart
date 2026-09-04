import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/downloads/providers/bookmark_outbox_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/store/bookmarks_dao.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

class BookmarksState {
  const BookmarksState({
    required this.bookmarks,
    this.actionPending = false,
  });

  final List<Bookmark> bookmarks;
  final bool actionPending;

  BookmarksState copyWith({
    List<Bookmark>? bookmarks,
    bool? actionPending,
  }) =>
      BookmarksState(
        bookmarks: bookmarks ?? this.bookmarks,
        actionPending: actionPending ?? this.actionPending,
      );
}

final bookmarksProvider =
    AsyncNotifierProvider.autoDispose<BookmarksNotifier, BookmarksState>(
  BookmarksNotifier.new,
  name: 'bookmarks',
);

/// Backs the Bookmarks screen — **device first**.
///
/// The list is read off the on-device `bookmarks` table, so the screen works
/// on a plane, in a lift, and on a phone that has not reached the server in a
/// week. The server is reconciled *behind* that read
/// ([BookmarkOutboxController.sync]) and the list re-read if anything changed;
/// a failed sync costs the screen nothing at all.
///
/// Deleting goes through the outbox for the same reason: it tombstones
/// locally and pushes best-effort, so removing a bookmark with no signal is an
/// ordinary success rather than an error.
class BookmarksNotifier extends AutoDisposeAsyncNotifier<BookmarksState> {
  /// One background reconcile per screen visit — the sync writes [state], and
  /// without this that write would re-enter [build] and start another.
  bool _syncStarted = false;

  /// Riverpod 2.6 has no `ref.mounted`, and a sync that outlives the screen
  /// would otherwise write to a disposed notifier.
  bool _disposed = false;

  @override
  Future<BookmarksState> build() async {
    ref.onDispose(() => _disposed = true);
    final state = await _fetch();
    // Only worth doing when there is a device table to reconcile INTO. With
    // no scope, [_fetch] already asked the server and there is nothing a sync
    // could add — asking twice would just be a second round trip.
    if (!_syncStarted && ref.read(downloadsStoreProvider) != null) {
      _syncStarted = true;
      unawaited(_syncInBackground());
    }
    return state;
  }

  /// Pull-to-refresh: reconcile with the server *first*, then re-read the
  /// device. The user asked for the freshest answer and is watching a
  /// spinner, so waiting on the round trip is what they meant.
  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      await ref.read(bookmarkOutboxControllerProvider).sync();
      return _fetch();
    });
  }

  Future<void> _syncInBackground() async {
    final changed = await ref.read(bookmarkOutboxControllerProvider).sync();
    // Nothing came back that the device did not already hold, so the list on
    // screen is still right — re-reading it would only make it flicker.
    if (!changed || _disposed) return;
    final refreshed = await _fetch();
    if (_disposed) return;
    state = AsyncData(
      refreshed.copyWith(
        actionPending: state.valueOrNull?.actionPending ?? false,
      ),
    );
  }

  Future<BookmarksState> _fetch() async {
    final store = ref.read(downloadsStoreProvider);
    if (store != null) {
      return BookmarksState(bookmarks: await store.listBookmarks());
    }
    // No resolvable `(user, profile)` scope — there is no device table to
    // read, so the server is the only thing that can answer at all.
    final result = await ref.read(readerRepositoryProvider).listBookmarks();
    if (result.isErr) throw result.error;
    return BookmarksState(bookmarks: result.value);
  }

  /// Remove a bookmark. Sets `actionPending` optimistically so the Remove
  /// button disables itself the instant it is tapped, preventing a double tap
  /// from firing a second delete before the first completes.
  ///
  /// The device path tombstones and queues, and cannot fail; the scopeless
  /// path (no store to write to) deletes straight on the server and can, so
  /// its error is returned and the row stays on screen.
  Future<AppError?> deleteBookmark(Bookmark bookmark) async {
    final current = state.valueOrNull;
    if (current != null) {
      state = AsyncData(current.copyWith(actionPending: true));
    }

    final store = ref.read(downloadsStoreProvider);
    if (store == null) {
      final id = bookmark.id;
      AppError? error;
      if (id == null) {
        error = const UnknownError(
          message: 'This bookmark has not reached the server yet.',
        );
      } else {
        final result =
            await ref.read(readerRepositoryProvider).deleteBookmark(id);
        if (result.isErr) error = result.error;
      }
      if (error != null) {
        if (current != null && !_disposed) {
          state = AsyncData(current.copyWith(actionPending: false));
        }
        return error;
      }
    } else {
      await ref.read(bookmarkOutboxControllerProvider).remove(bookmark.clientId);
    }

    if (_disposed) return null;
    state = AsyncData(await _fetch());
    return null;
  }
}
