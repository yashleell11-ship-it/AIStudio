import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/updates/models/series_tracker.dart';
import 'package:aistudio_mobile/features/updates/models/update_notification.dart';
import 'package:aistudio_mobile/features/updates/repositories/updates_repository.dart';
import 'package:dio/dio.dart';

class UpdatesRepositoryImpl implements UpdatesRepository {
  const UpdatesRepositoryImpl(this._dio);

  final Dio _dio;

  @override
  Future<Result<List<UpdateNotification>>> listNotifications({
    bool unreadOnly = false,
    int limit = 100,
  }) async {
    try {
      final r = await _dio.get<List<dynamic>>(
        '/updates/notifications',
        queryParameters: {
          if (unreadOnly) 'unread_only': true,
          'limit': limit,
        },
      );
      final items = (r.data ?? [])
          .map((e) => UpdateNotification.fromJson(e as Map<String, dynamic>))
          .toList();
      return Ok(items);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<int>> getUnreadCount() async {
    try {
      final r = await _dio.get<Map<String, dynamic>>('/updates/notifications/unread-count');
      return Ok(r.data!['count'] as int);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<void>> markRead(int notificationId) async {
    try {
      await _dio.patch<void>('/updates/notifications/$notificationId/read');
      return const Ok(null);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<void>> markAllRead() async {
    try {
      await _dio.post<void>('/updates/notifications/read-all');
      return const Ok(null);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<List<SeriesTracker>>> listTrackers() async {
    try {
      final r = await _dio.get<List<dynamic>>('/updates/trackers');
      final items = (r.data ?? [])
          .map((e) => SeriesTracker.fromJson(e as Map<String, dynamic>))
          .toList();
      return Ok(items);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<void>> followSeries({
    required String source,
    required String seriesId,
    required String seriesTitle,
  }) async {
    try {
      await _dio.post<void>(
        '/updates/trackers/follow',
        data: {
          'source': source,
          'series_id': seriesId,
          'series_title': seriesTitle,
        },
      );
      return const Ok(null);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<void>> deleteTracker(int trackerId) async {
    try {
      await _dio.delete<void>('/updates/trackers/$trackerId');
      return const Ok(null);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<void>> updateTracker(
    int trackerId, {
    bool? autoDownload,
  }) async {
    try {
      await _dio.patch<void>(
        '/updates/trackers/$trackerId',
        data: {
          if (autoDownload != null) 'auto_download': autoDownload,
        },
      );
      return const Ok(null);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<void>> triggerCheck() async {
    try {
      await _dio.post<void>('/updates/check');
      return const Ok(null);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  AppError _err(DioException e) {
    if (e.error is AppError) return e.error! as AppError;
    return UnknownError(message: e.message ?? 'Dio error', cause: e);
  }
}
