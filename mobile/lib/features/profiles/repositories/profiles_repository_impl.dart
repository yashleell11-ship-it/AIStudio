import 'package:dio/dio.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/profiles/models/mood.dart';
import 'package:manhwamaniacs/features/profiles/models/profile.dart';
import 'package:manhwamaniacs/features/profiles/repositories/profiles_repository.dart';

class ProfilesRepositoryImpl implements ProfilesRepository {
  const ProfilesRepositoryImpl(this._dio);

  final Dio _dio;

  @override
  Future<Result<List<Profile>>> list() async {
    try {
      final r = await _dio.get<List<dynamic>>('/profiles');
      final items = (r.data ?? [])
          .map((e) => Profile.fromJson(e as Map<String, dynamic>))
          .toList();
      return Ok(items);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<Profile>> create({
    required String name,
    required String avatarKey,
    required Mood mood,
    int? sortOrder,
    bool? matureContentEnabled,
  }) async {
    try {
      final r = await _dio.post<Map<String, dynamic>>(
        '/profiles',
        data: {
          'name': name,
          'avatar_key': avatarKey,
          'mood': mood.wire,
          if (sortOrder != null) 'sort_order': sortOrder,
          if (matureContentEnabled != null)
            'mature_content_enabled': matureContentEnabled,
        },
      );
      return Ok(Profile.fromJson(r.data!));
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<Profile>> update(
    int id, {
    String? name,
    String? avatarKey,
    Mood? mood,
    int? sortOrder,
    bool? matureContentEnabled,
  }) async {
    try {
      final r = await _dio.patch<Map<String, dynamic>>(
        '/profiles/$id',
        data: {
          if (name != null) 'name': name,
          if (avatarKey != null) 'avatar_key': avatarKey,
          if (mood != null) 'mood': mood.wire,
          if (sortOrder != null) 'sort_order': sortOrder,
          if (matureContentEnabled != null)
            'mature_content_enabled': matureContentEnabled,
        },
      );
      return Ok(Profile.fromJson(r.data!));
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<void>> remove(int id) async {
    try {
      await _dio.delete<void>('/profiles/$id');
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
