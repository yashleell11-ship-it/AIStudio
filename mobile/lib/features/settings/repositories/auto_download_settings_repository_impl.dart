import 'package:dio/dio.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/settings/repositories/auto_download_settings_repository.dart';

class AutoDownloadSettingsRepositoryImpl
    implements AutoDownloadSettingsRepository {
  const AutoDownloadSettingsRepositoryImpl(this._dio);

  final Dio _dio;

  static const String _key = 'auto_download_enabled';

  @override
  Future<Result<bool>> getAutoDownloadEnabled() async {
    try {
      final r = await _dio.get<Map<String, dynamic>>('/updates/settings');
      // Absent => off. The server default is False on a fresh install
      // (backend/services/update_service.py:280), and "unknown" must never
      // render as an armed auto-download switch.
      return Ok((r.data?[_key] as bool?) ?? false);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<bool>> setAutoDownloadEnabled(bool enabled) async {
    try {
      // PUT is a partial update server-side (`model_dump(exclude_none=True)`),
      // so sending this one key leaves the check interval and notification
      // settings alone.
      final r = await _dio.put<Map<String, dynamic>>(
        '/updates/settings',
        data: {_key: enabled},
      );
      return Ok((r.data?[_key] as bool?) ?? enabled);
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
