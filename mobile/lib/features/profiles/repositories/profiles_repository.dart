import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/profiles/models/mood.dart';
import 'package:manhwamaniacs/features/profiles/models/profile.dart';

/// Thin contract over the backend `/profiles` routes. Every call rides the
/// bearer token via the shared Dio auth interceptor; the profiles are scoped to
/// the signed-in account server-side (household model).
abstract interface class ProfilesRepository {
  /// All profiles for the signed-in account, ordered by `sort_order`.
  Future<Result<List<Profile>>> list();

  Future<Result<Profile>> create({
    required String name,
    required String avatarKey,
    required Mood mood,
    int? sortOrder,
    bool? matureContentEnabled,
  });

  Future<Result<Profile>> update(
    int id, {
    String? name,
    String? avatarKey,
    Mood? mood,
    int? sortOrder,
    bool? matureContentEnabled,
  });

  Future<Result<void>> remove(int id);
}
