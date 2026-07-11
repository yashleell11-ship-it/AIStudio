import 'package:dio/dio.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/models/download_item.dart';
import 'package:manhwamaniacs/features/downloads/models/download_metrics.dart';
import 'package:manhwamaniacs/features/downloads/models/download_settings.dart';
import 'package:manhwamaniacs/features/downloads/models/queue_download_response.dart';
import 'package:manhwamaniacs/features/downloads/repositories/downloads_repository.dart';

class DownloadsRepositoryImpl implements DownloadsRepository {
  const DownloadsRepositoryImpl(this._dio);

  final Dio _dio;

  @override
  Future<Result<List<DownloadItem>>> listDownloads() => _list(
        '/downloads',
        DownloadItem.fromJson,
      );

  @override
  Future<Result<DownloadMetrics>> getMetrics() => _obj(
        '/downloads/metrics',
        DownloadMetrics.fromJson,
      );

  @override
  Future<Result<DownloadSettings>> getSettings() => _obj(
        '/downloads/settings',
        DownloadSettings.fromJson,
      );

  @override
  Future<Result<DownloadSettings>> updateSettings(DownloadSettings settings) =>
      _objPut('/downloads/settings', settings.toUpdateJson(), DownloadSettings.fromJson);

  @override
  Future<Result<QueueDownloadResponse>> queueChapters({
    required String sourceId,
    required String seriesId,
    required List<String> chapterIds,
    String? seriesTitle,
    int? priority,
  }) =>
      _objPost(
        '/downloads/chapters',
        {
          'source_id': sourceId,
          'series_id': seriesId,
          'chapter_ids': chapterIds,
          if (seriesTitle != null) 'series_title': seriesTitle,
          if (priority != null) 'priority': priority,
        },
        QueueDownloadResponse.fromJson,
      );

  @override
  Future<Result<QueueDownloadResponse>> queueSeries({
    required String sourceId,
    required String seriesId,
    int? priority,
  }) =>
      _objPost(
        '/downloads/series',
        {
          'source_id': sourceId,
          'series_id': seriesId,
          if (priority != null) 'priority': priority,
        },
        QueueDownloadResponse.fromJson,
      );

  @override
  Future<Result<void>> pauseDownload(int downloadId) =>
      _void(() => _dio.post<dynamic>('/downloads/$downloadId/pause'));

  @override
  Future<Result<void>> resumeDownload(int downloadId) =>
      _void(() => _dio.post<dynamic>('/downloads/$downloadId/resume'));

  @override
  Future<Result<void>> cancelDownload(int downloadId) =>
      _void(() => _dio.post<dynamic>('/downloads/$downloadId/cancel'));

  @override
  Future<Result<void>> retryDownload(int downloadId) =>
      _void(() => _dio.post<dynamic>('/downloads/$downloadId/retry'));

  @override
  Future<Result<void>> moveDownload(int downloadId, {required String direction}) =>
      _void(
        () => _dio.post<dynamic>(
          '/downloads/$downloadId/move',
          data: {'direction': direction},
        ),
      );

  @override
  Future<Result<int>> pauseAll() =>
      _bulkInt(() => _dio.post<Map<String, dynamic>>('/downloads/pause-all'));

  @override
  Future<Result<int>> resumeAll() =>
      _bulkInt(() => _dio.post<Map<String, dynamic>>('/downloads/resume-all'));

  @override
  Future<Result<int>> cancelAll() =>
      _bulkInt(() => _dio.post<Map<String, dynamic>>('/downloads/cancel-all'));

  @override
  Future<Result<int>> pauseSeries({
    required String sourceId,
    required String seriesId,
  }) =>
      _bulkInt(
        () => _dio.post<Map<String, dynamic>>(
          '/downloads/series/pause',
          data: {'source_id': sourceId, 'series_id': seriesId},
        ),
      );

  @override
  Future<Result<int>> resumeSeries({
    required String sourceId,
    required String seriesId,
  }) =>
      _bulkInt(
        () => _dio.post<Map<String, dynamic>>(
          '/downloads/series/resume',
          data: {'source_id': sourceId, 'series_id': seriesId},
        ),
      );

  @override
  Future<Result<int>> cancelSeries({
    required String sourceId,
    required String seriesId,
  }) =>
      _bulkInt(
        () => _dio.post<Map<String, dynamic>>(
          '/downloads/series/cancel',
          data: {'source_id': sourceId, 'series_id': seriesId},
        ),
      );

  // ── Helpers ───────────────────────────────────────────────────────────────

  Future<Result<T>> _obj<T>(
    String path,
    T Function(Map<String, dynamic>) fromJson,
  ) async {
    try {
      final r = await _dio.get<Map<String, dynamic>>(path);
      return Ok(fromJson(r.data!));
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  Future<Result<T>> _objPost<T>(
    String path,
    Map<String, dynamic> body,
    T Function(Map<String, dynamic>) fromJson,
  ) async {
    try {
      final r = await _dio.post<Map<String, dynamic>>(path, data: body);
      return Ok(fromJson(r.data!));
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  Future<Result<T>> _objPut<T>(
    String path,
    Map<String, dynamic> body,
    T Function(Map<String, dynamic>) fromJson,
  ) async {
    try {
      final r = await _dio.put<Map<String, dynamic>>(path, data: body);
      return Ok(fromJson(r.data!));
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  Future<Result<List<T>>> _list<T>(
    String path,
    T Function(Map<String, dynamic>) fromJson,
  ) async {
    try {
      final r = await _dio.get<List<dynamic>>(path);
      final items = (r.data ?? [])
          .map((e) => fromJson(e as Map<String, dynamic>))
          .toList();
      return Ok(items);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  Future<Result<int>> _bulkInt(
    Future<Response<Map<String, dynamic>>> Function() call,
  ) async {
    try {
      final response = await call();
      final affected = response.data?['affected'];
      return Ok(affected is int ? affected : 0);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  Future<Result<void>> _void(Future<dynamic> Function() call) async {
    try {
      await call();
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
