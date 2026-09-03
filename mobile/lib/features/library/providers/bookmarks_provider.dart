import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
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

/// Backs the Bookmark Manager screen: lists bookmarks across every series
/// and lets the user remove one. Mirrors [UpdatesNotifier]'s
/// list+action(actionPending)+refresh shape so the delete button gets the
/// same immediate busy/disabled state and double-tap protection as
/// Follow/Unfollow.
class BookmarksNotifier extends AutoDisposeAsyncNotifier<BookmarksState> {
  @override
  Future<BookmarksState> build() async => _fetch();

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(_fetch);
  }

  Future<BookmarksState> _fetch() async {
    final repo = ref.read(readerRepositoryProvider);
    final result = await repo.listBookmarks();
    if (result.isErr) throw result.error;
    return BookmarksState(bookmarks: result.value);
  }

  /// Remove a bookmark. Sets `actionPending` optimistically so the Remove
  /// button disables itself the instant it is tapped, preventing a double
  /// tap from firing a second delete before the first completes.
  Future<AppError?> deleteBookmark(int bookmarkId) async {
    final current = state.valueOrNull;
    if (current != null) {
      state = AsyncData(current.copyWith(actionPending: true));
    }
    final repo = ref.read(readerRepositoryProvider);
    final result = await repo.deleteBookmark(bookmarkId);
    if (result.isErr) {
      if (current != null) {
        state = AsyncData(current.copyWith(actionPending: false));
      }
      return result.error;
    }
    await refresh();
    return null;
  }
}
