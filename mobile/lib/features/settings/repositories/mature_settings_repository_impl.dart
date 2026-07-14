import 'package:dio/dio.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/settings/repositories/mature_settings_repository.dart';

class MatureSettingsRepositoryImpl implements MatureSettingsRepository {
  const MatureSettingsRepositoryImpl(this._dio);

  final Dio _dio;

  static const String _key = 'mature_content_enabled';

  @override
  Future<Result<bool>> getMatureEnabled() async {
    try {
      final r = await _dio.get<Map<String, dynamic>>('/settings');
      return Ok((r.data?[_key] as bool?) ?? false);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<bool>> setMatureEnabled(bool enabled) async {
    try {
      final r = await _dio.put<Map<String, dynamic>>(
        '/settings',
        data: {_key: enabled},
      );
      // Trust the server's echoed value; fall back to the requested one when
      // the response body omits it.
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
