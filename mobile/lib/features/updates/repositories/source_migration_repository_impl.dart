import 'package:dio/dio.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/updates/models/source_migration.dart';
import 'package:manhwamaniacs/features/updates/repositories/source_migration_repository.dart';

class SourceMigrationRepositoryImpl implements SourceMigrationRepository {
  const SourceMigrationRepositoryImpl(this._dio);

  final Dio _dio;

  @override
  Future<Result<MigrationCandidateList>> candidates(
    int trackerId, {
    String? query,
    int perPage = 10,
  }) async {
    try {
      final trimmed = query?.trim();
      final r = await _dio.get<Map<String, dynamic>>(
        '/updates/trackers/$trackerId/migration-candidates',
        queryParameters: {
          // Omitted rather than sent empty so the server falls back to the
          // followed title, which is the documented default.
          if (trimmed != null && trimmed.isNotEmpty) 'q': trimmed,
          'per_page': perPage,
        },
        // The fan-out queries every browsable connector in parallel under its
        // own whole-request deadline; the client's default receive timeout is
        // far shorter than that, and cutting it off client-side would report a
        // timeout for a request the server was about to answer.
        options: Options(receiveTimeout: const Duration(seconds: 90)),
      );
      return Ok(MigrationCandidateList.fromJson(r.data ?? const {}));
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<MigrationPlan>> migrate(
    int trackerId, {
    required String targetSource,
    required String targetSeriesId,
    String? targetSeriesTitle,
    double chapterOffset = 0,
    bool dryRun = true,
    bool merge = false,
    String? expectedChapterMapHash,
  }) async {
    try {
      final r = await _dio.post<Map<String, dynamic>>(
        '/updates/trackers/$trackerId/migrate',
        data: {
          'target_source': targetSource,
          'target_series_id': targetSeriesId,
          if (targetSeriesTitle != null) 'target_series_title': targetSeriesTitle,
          'chapter_offset': chapterOffset,
          'dry_run': dryRun,
          'merge': merge,
          if (expectedChapterMapHash != null)
            'expected_chapter_map_hash': expectedChapterMapHash,
        },
        // Both catalogs are fetched server-side before any write opens, so even
        // the commit can sit behind two scraper calls.
        options: Options(receiveTimeout: const Duration(seconds: 90)),
      );
      return Ok(MigrationPlan.fromJson(r.data ?? const {}));
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
