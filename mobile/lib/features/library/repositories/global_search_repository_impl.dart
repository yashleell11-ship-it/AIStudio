import 'package:dio/dio.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/library/models/global_search_result.dart';
import 'package:manhwamaniacs/features/library/repositories/global_search_repository.dart';

class GlobalSearchRepositoryImpl implements GlobalSearchRepository {
  GlobalSearchRepositoryImpl(this._dio);

  final Dio _dio;

  @override
  Future<Result<GlobalSearchResult>> search(
    String query, {
    int page = 1,
    int perPage = 40,
  }) async {
    try {
      final r = await _dio.get<Map<String, dynamic>>(
        '/sources/search',
        queryParameters: {
          'q': query,
          'page': page,
          'per_page': perPage,
        },
      );
      return Ok(GlobalSearchResult.fromJson(r.data ?? const {}));
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
