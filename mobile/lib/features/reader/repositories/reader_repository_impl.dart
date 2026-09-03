import 'package:dio/dio.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository.dart';

class ReaderRepositoryImpl implements ReaderRepository {
  const ReaderRepositoryImpl(this._dio);

  final Dio _dio;

  @override
  Future<Result<ChapterManifest>> manifest({
    required String sourceId,
    required String seriesKey,
    required String chapterKey,
  }) async {
    try {
      final r = await _dio.get<Map<String, dynamic>>(
        '/reader/chapter/manifest',
        queryParameters: {
          'source': sourceId,
          'series': seriesKey,
          'chapter': chapterKey,
        },
      );
      return Ok(ChapterManifest.fromJson(r.data!));
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<ReadingProgress>> saveProgress(ProgressPush push) async {
    try {
      final r = await _dio.post<Map<String, dynamic>>(
        '/reader/progress',
        data: push.toJson(),
      );
      return Ok(ReadingProgress.fromJson(r.data!));
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<({int saved, int advanced})>> saveProgressBatch(
    List<ProgressPush> pushes,
  ) async {
    try {
      final r = await _dio.post<Map<String, dynamic>>(
        '/reader/progress/batch',
        data: [for (final push in pushes) push.toJson()],
      );
      final data = r.data!;
      return Ok((
        saved: data['saved'] as int,
        advanced: data['advanced'] as int,
      ));
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<List<ReadingProgress>>> seriesProgress({
    required String sourceId,
    required String seriesKey,
  }) async {
    try {
      final r = await _dio.get<List<dynamic>>(
        '/reader/progress/series',
        queryParameters: {'source': sourceId, 'series': seriesKey},
      );
      final items = (r.data ?? [])
          .map((e) => ReadingProgress.fromJson(e as Map<String, dynamic>))
          .toList();
      return Ok(items);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<Bookmark>> addBookmark({
    required String sourceId,
    required String seriesKey,
    required String chapterKey,
    required int page,
    String? note,
  }) async {
    try {
      final r = await _dio.post<Map<String, dynamic>>(
        '/reader/bookmark',
        data: {
          'source_id': sourceId,
          'series_key': seriesKey,
          'chapter_key': chapterKey,
          'page': page,
          if (note != null) 'note': note,
        },
      );
      return Ok(Bookmark.fromJson(r.data!));
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<List<Bookmark>>> listBookmarks({
    String? sourceId,
    String? seriesKey,
  }) async {
    try {
      final r = await _dio.get<List<dynamic>>(
        '/reader/bookmarks',
        queryParameters: {
          if (sourceId != null) 'source': sourceId,
          if (seriesKey != null) 'series': seriesKey,
        },
      );
      final items = (r.data ?? [])
          .map((e) => Bookmark.fromJson(e as Map<String, dynamic>))
          .toList();
      return Ok(items);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) async {
    try {
      await _dio.delete<void>('/reader/bookmarks/$bookmarkId');
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
