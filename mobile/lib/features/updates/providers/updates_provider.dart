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
    final repo = ref.read(updatesRepositoryProvider);
    final result = await repo.deleteTracker(id);
    if (result.isErr) return result.error;
    await refresh();
    return null;
  }
}
