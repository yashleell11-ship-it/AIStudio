import 'package:dio/dio.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/auth/models/auth_response.dart';
import 'package:manhwamaniacs/features/auth/models/auth_user.dart';
import 'package:manhwamaniacs/features/auth/models/bootstrap_status.dart';
import 'package:manhwamaniacs/features/auth/models/user_session.dart';
import 'package:manhwamaniacs/features/auth/repositories/auth_repository.dart';

class AuthRepositoryImpl implements AuthRepository {
  const AuthRepositoryImpl(this._dio);

  final Dio _dio;

  @override
  Future<Result<BootstrapStatus>> bootstrapStatus() => _obj(
        '/auth/bootstrap-status',
        BootstrapStatus.fromJson,
      );

  @override
  Future<Result<AuthResponse>> login({
    required String username,
    required String password,
    bool remember = true,
  }) =>
      _objPost(
        '/auth/login',
        {
          'username': username,
          'password': password,
          'remember': remember,
        },
        AuthResponse.fromJson,
      );

  @override
  Future<Result<AuthResponse>> register({
    required String username,
    required String password,
    String? email,
    String? displayName,
    String? inviteCode,
    bool remember = true,
  }) =>
      _objPost(
        '/auth/register',
        {
          'username': username,
          'password': password,
          if (email != null && email.isNotEmpty) 'email': email,
          if (displayName != null && displayName.isNotEmpty)
            'display_name': displayName,
          if (inviteCode != null && inviteCode.isNotEmpty)
            'invite_code': inviteCode,
          'remember': remember,
        },
        AuthResponse.fromJson,
      );

  @override
  Future<Result<void>> logout() =>
      _void(() => _dio.post<dynamic>('/auth/logout'));

  @override
  Future<Result<AuthUser>> me() => _obj('/auth/me', AuthUser.fromJson);

  // Both passwords travel in the POST body and nowhere else — never a query
  // parameter, which would land them in server logs and any proxy in between.
  @override
  Future<Result<void>> changePassword({
    required String currentPassword,
    required String newPassword,
  }) =>
      _void(
        () => _dio.post<dynamic>(
          '/auth/change-password',
          data: {
            'current_password': currentPassword,
            'new_password': newPassword,
          },
        ),
      );

  @override
  Future<Result<List<UserSession>>> sessions() async {
    try {
      final r = await _dio.get<List<dynamic>>('/auth/sessions');
      final items = (r.data ?? [])
          .map((e) => UserSession.fromJson(e as Map<String, dynamic>))
          .toList();
      return Ok(items);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<void>> revokeSession(int sessionId) =>
      _void(() => _dio.delete<dynamic>('/auth/sessions/$sessionId'));

  @override
  Future<Result<void>> logoutAll() =>
      _void(() => _dio.post<dynamic>('/auth/logout-all'));

  // ── Helpers ─────────────────────────────────────────────────────────────

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
