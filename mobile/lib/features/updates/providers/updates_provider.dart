import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/updates/models/update_notification.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

class UpdatesState {
  const UpdatesState({
    required this.notifications,
    required this.unreadCount,
    required this.followed,
    this.actionPending = false,
  });

  final List<UpdateNotification> notifications;
  final int unreadCount;

  /// Every series the active profile follows — the shared cache the Updates
  /// tab, the Library dashboard's "followed" shelf, and every
  /// `SeriesFollowButton` all watch.
  final List<FollowedSeries> followed;
  final bool actionPending;

  UpdatesState copyWith({
    List<UpdateNotification>? notifications,
    int? unreadCount,
    List<FollowedSeries>? followed,
    bool? actionPending,
  }) =>
      UpdatesState(
        notifications: notifications ?? this.notifications,
        unreadCount: unreadCount ?? this.unreadCount,
        followed: followed ?? this.followed,
        actionPending: actionPending ?? this.actionPending,
      );
}

final updatesProvider =
    AsyncNotifierProvider.autoDispose<UpdatesNotifier, UpdatesState>(
  UpdatesNotifier.new,
  name: 'updates',
);

/// Followed series fetched per refresh — generous enough to cover a real
/// household's library in one unpaginated call (mirrors the old trackers
/// list, which had no pagination either).
const _followedIndexPageSize = 200;

class UpdatesNotifier extends AutoDisposeAsyncNotifier<UpdatesState> {
  @override
  Future<UpdatesState> build() async => _fetch();

  Future<void> refresh() async {
    // Keep the current data visible while re-fetching so action-driven reloads
    // (mark read, check now, unfollow) and pull-to-refresh don't blank the
    // whole screen to a skeleton. The RefreshIndicator spinner and optimistic
    // actionPending state provide the loading affordance; first load is
    // covered by build().
    state = await AsyncValue.guard(_fetch);
  }

  Future<UpdatesState> _fetch() async {
    final updatesRepo = ref.read(updatesRepositoryProvider);
    final libraryRepo = ref.read(libraryRepositoryProvider);
    final notifications = await updatesRepo.listNotifications();
    final unread = await updatesRepo.getUnreadCount();
    final followed = await libraryRepo.listSeries(perPage: _followedIndexPageSize);
    if (notifications.isErr) throw notifications.error;
    if (unread.isErr) throw unread.error;
    if (followed.isErr) throw followed.error;
    return UpdatesState(
      notifications: notifications.value,
      unreadCount: unread.value,
      followed: followed.value.items,
    );
  }

  Future<AppError?> markRead(int id) async {
    final repo = ref.read(updatesRepositoryProvider);
    final result = await repo.markRead(id);
    if (result.isErr) return result.error;
    await refresh();
    return null;
  }

  Future<AppError?> markAllRead() async {
    final repo = ref.read(updatesRepositoryProvider);
    final result = await repo.markAllRead();
    if (result.isErr) return result.error;
    await refresh();
    return null;
  }

  Future<AppError?> triggerCheck() async {
    final repo = ref.read(updatesRepositoryProvider);
    final result = await repo.triggerCheck();
    if (result.isErr) return result.error;
    await refresh();
    return null;
  }

  Future<AppError?> unfollow(int followedId) async {
    final current = state.valueOrNull;
    if (current != null) {
      state = AsyncData(current.copyWith(actionPending: true));
    }
    final repo = ref.read(libraryRepositoryProvider);
    final result = await repo.unfollow(followedId);
    if (result.isErr) {
      if (current != null) {
        state = AsyncData(current.copyWith(actionPending: false));
      }
      return result.error;
    }
    await refresh();
    return null;
  }

  /// Follow a source series for new-chapter notifications. Idempotent on the
  /// server side (returns the existing row when already followed), but we
  /// still refresh so the followed list reflects the change immediately.
  /// Sets `actionPending` optimistically so the Follow button shows a busy
  /// state the instant it is tapped, before the network round-trip completes.
  Future<AppError?> followSeries({
    required String sourceId,
    required String seriesKey,
  }) async {
    final current = state.valueOrNull;
    if (current != null) {
      state = AsyncData(current.copyWith(actionPending: true));
    }
    final repo = ref.read(libraryRepositoryProvider);
    final result = await repo.follow(sourceId: sourceId, seriesKey: seriesKey);
    if (result.isErr) {
      if (current != null) {
        state = AsyncData(current.copyWith(actionPending: false));
      }
      return result.error;
    }
    await refresh();
    return null;
  }

  /// Takes [followedId] out of the shared followed list and reports the slot
  /// it held, or -1 when this cache does not have it.
  ///
  /// Spliced rather than invalidated because the Library tab is drawn from
  /// this cache and rebuilding it costs three requests: blanking the whole
  /// shelf to a skeleton to delete one card is how a working delete reads as a
  /// broken one.
  ///
  /// Its notifications go with it, because they go with it on the server —
  /// `update_notifications.followed_series_id` is `ON DELETE CASCADE`, so
  /// keeping them here would leave the Updates tab listing chapters of a
  /// series nobody follows and the unread badge counting rows that no longer
  /// exist. An undo re-follows into a new row with no notification history,
  /// which is exactly what the server will report.
  ///
  /// State only; the removal itself lives in `librarySeriesActionsProvider`,
  /// which is what drives this.
  int forgetFollowed(int followedId) {
    final current = state.valueOrNull;
    if (current == null) return -1;
    final index =
        current.followed.indexWhere((series) => series.id == followedId);
    if (index < 0) return -1;

    var unread = current.unreadCount;
    final notifications = <UpdateNotification>[];
    for (final notification in current.notifications) {
      if (notification.followedSeriesId != followedId) {
        notifications.add(notification);
      } else if (!notification.isRead) {
        unread--;
      }
    }

    state = AsyncData(
      current.copyWith(
        followed: [...current.followed]..removeAt(index),
        notifications: notifications,
        unreadCount: unread < 0 ? 0 : unread,
      ),
    );
    return index;
  }

  /// Puts [series] into the shared followed list: in place when the row is
  /// already there, otherwise back in the slot an undo pulled it from —
  /// clamped, because a refresh may have reshaped the list while the request
  /// was in flight, and appended when there is no slot to honour.
  void rememberFollowed(FollowedSeries series, {int index = -1}) {
    final current = state.valueOrNull;
    if (current == null) return;
    final at = current.followed.indexWhere((item) => item.id == series.id);
    if (at >= 0) {
      state = AsyncData(
        current.copyWith(followed: [...current.followed]..[at] = series),
      );
      return;
    }
    final slot = index < 0
        ? current.followed.length
        : index.clamp(0, current.followed.length);
    state = AsyncData(
      current.copyWith(
        followed: [...current.followed]..insert(slot, series),
      ),
    );
  }

  /// Returns the followed-series row for the given source+series, or null if
  /// the active profile is not following it. Used by [SeriesFollowButton] to
  /// drive the Follow / Unfollow label and action.
  FollowedSeries? followedFor({required String sourceId, required String seriesKey}) {
    final value = state.valueOrNull;
    if (value == null) return null;
    for (final series in value.followed) {
      if (series.sourceId == sourceId && series.seriesKey == seriesKey) {
        return series;
      }
    }
    return null;
  }
}
