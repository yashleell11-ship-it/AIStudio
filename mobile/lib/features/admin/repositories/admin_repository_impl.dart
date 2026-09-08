import 'package:dio/dio.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/admin/models/account.dart';
import 'package:manhwamaniacs/features/admin/repositories/admin_repository.dart';

class AdminRepositoryImpl implements AdminRepository {
  const AdminRepositoryImpl(this._dio);

  final Dio _dio;

  @override
  Future<Result<List<Account>>> listAccounts() async {
    try {
      final r = await _dio.get<List<dynamic>>('/auth/users');
      final rows = r.data ?? const <dynamic>[];
      return Ok([
        for (final row in rows)
          if (row is Map<String, dynamic>) Account.fromJson(row),
      ]);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<Account>> setActive({
    required int id,
    required bool active,
  }) async {
    try {
      final r = await _dio.patch<Map<String, dynamic>>(
        '/auth/users/$id',
        data: {'is_active': active},
      );
      return Ok(Account.fromJson(r.data!));
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<void>> deleteAccount(int id) async {
    try {
      // 204, no body.
      await _dio.delete<void>('/auth/users/$id');
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
