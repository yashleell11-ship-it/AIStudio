import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/updates/models/series_tracker.dart';
import 'package:aistudio_mobile/features/updates/models/update_notification.dart';

abstract interface class UpdatesRepository {
  Future<Result<List<UpdateNotification>>> listNotifications({
    bool unreadOnly = false,
    int limit = 100,
  });

  Future<Result<int>> getUnreadCount();

  Future<Result<void>> markRead(int notificationId);

  Future<Result<void>> markAllRead();

  Future<Result<List<SeriesTracker>>> listTrackers();

  Future<Result<void>> followSeries({
    required String source,
    required String seriesId,
    required String seriesTitle,
  });

  Future<Result<void>> deleteTracker(int trackerId);

  Future<Result<void>> triggerCheck();
}
