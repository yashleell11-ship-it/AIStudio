import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/updates/models/series_tracker.dart';
import 'package:aistudio_mobile/features/updates/models/update_notification.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class UpdatesState {
  const UpdatesState({
    required this.notifications,
    required this.unreadCount,
    required this.trackers,
    this.actionPending = false,
  });

  final List<UpdateNotification> notifications;
  final int unreadCount;
  final List<SeriesTracker> trackers;
  final bool actionPending;

  UpdatesState copyWith({
    List<UpdateNotification>? notifications,
    int? unreadCount,
    List<SeriesTracker>? trackers,
    bool? actionPending,
  }) =>
      UpdatesState(
        notifications: notifications ?? this.notifications,
        unreadCount: unreadCount ?? this.unreadCount,
        trackers: trackers ?? this.trackers,
        actionPending: actionPending ?? this.actionPending,
      );
}

final updatesProvider =
    AsyncNotifierProvider.autoDispose<UpdatesNotifier, UpdatesState>(
  UpdatesNotifier.new,
  name: 'updates',
);

class UpdatesNotifier extends AutoDisposeAsyncNotifier<UpdatesState> {
  @override
  Future<UpdatesState> build() async => _fetch();

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(_fetch);
  }

  Future<UpdatesState> _fetch() async {
    final repo = ref.read(updatesRepositoryProvider);
    final notifications = await repo.listNotifications(limit: 100);
    final unread = await repo.getUnreadCount();
    final trackers = await repo.listTrackers();
    if (notifications.isErr) throw notifications.error;
    if (unread.isErr) throw unread.error;
    if (trackers.isErr) throw trackers.error;
    return UpdatesState(
      notifications: notifications.value,
      unreadCount: unread.value,
      trackers: trackers.value,
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

  Future<AppError?> deleteTracker(int id) async {
    final current = state.valueOrNull;
    if (current != null) {
      state = AsyncData(current.copyWith(actionPending: true));
    }
    final repo = ref.read(updatesRepositoryProvider);
    final result = await repo.deleteTracker(id);
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
  /// server side, but we still refresh so the tracker list reflects the
  /// change immediately. Sets `actionPending` optimistically (mirroring
  /// DownloadsNotifier._runAction) so the Follow button shows a busy state
  /// the instant it is tapped, before the network round-trip completes.
  Future<AppError?> followSeries({
    required String source,
    required String seriesId,
    required String seriesTitle,
  }) async {
    final current = state.valueOrNull;
    if (current != null) {
      state = AsyncData(current.copyWith(actionPending: true));
    }
    final repo = ref.read(updatesRepositoryProvider);
    final result = await repo.followSeries(
      source: source,
      seriesId: seriesId,
      seriesTitle: seriesTitle,
    );
    if (result.isErr) {
      if (current != null) {
        state = AsyncData(current.copyWith(actionPending: false));
      }
      return result.error;
    }
    await refresh();
    return null;
  }

  Future<AppError?> setTrackerAutoDownload(int id, bool enabled) async {
    final current = state.valueOrNull;
    if (current != null) {
      state = AsyncData(current.copyWith(actionPending: true));
    }
    final repo = ref.read(updatesRepositoryProvider);
    final result = await repo.updateTracker(id, autoDownload: enabled);
    if (result.isErr) {
      if (current != null) {
        state = AsyncData(current.copyWith(actionPending: false));
      }
      return result.error;
    }
    await refresh();
    return null;
  }

  /// Returns the followed-tracker row for the given source+series, or null
  /// if the user is not following it. Used by the source detail screen to
  /// drive the Follow / Unfollow button label and action.
  SeriesTracker? trackerFor({required String source, required String seriesId}) {
    final value = state.valueOrNull;
    if (value == null) return null;
    for (final tracker in value.trackers) {
      if (tracker.trackKind == TrackKind.followed &&
          tracker.source == source &&
          tracker.seriesId == seriesId) {
        return tracker;
      }
    }
    return null;
  }
}
