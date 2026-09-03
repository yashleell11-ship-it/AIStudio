import 'package:dio/dio.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/ocr/models/ocr_coverage.dart';
import 'package:manhwamaniacs/features/ocr/models/ocr_search_result.dart';
import 'package:manhwamaniacs/features/ocr/models/page_text.dart';
import 'package:manhwamaniacs/features/ocr/repositories/ocr_repository.dart';
import 'package:manhwamaniacs/features/ocr/services/ocr_upload_payload.dart';

class OcrRepositoryImpl implements OcrRepository {
  const OcrRepositoryImpl(this._dio);

  final Dio _dio;

  @override
  Future<Result<int>> uploadChapter({
    required ChapterIdentity id,
    required List<PageText> pages,
    required String engine,
    double? chapterNumber,
    String? language,
  }) async {
    // Capping here, not at the call site: an over-limit body costs a 422 for
    // the entire chapter, and this is the last point before the wire where
    // that is still preventable.
    final capped = capOcrPagesForUpload(pages);
    if (capped.isEmpty) {
      return const Err(
        ValidationError('There is no recognized text to upload.'),
      );
    }

    try {
      final r = await _dio.post<Map<String, dynamic>>(
        '/ocr/chapter',
        data: {
          'source_id': id.sourceId,
          'series_key': id.seriesKey,
          'chapter_key': id.chapterKey,
          if (chapterNumber != null) 'chapter_number': chapterNumber,
          if (language != null) 'language': language,
          'engine': engine,
          'pages': [for (final page in capped) page.toJson()],
        },
      );
      return Ok((r.data?['word_count'] as num?)?.toInt() ?? 0);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<OcrCoverage>> coverage({
    required String sourceId,
    required String seriesKey,
  }) async {
    try {
      final r = await _dio.get<Map<String, dynamic>>(
        '/ocr/coverage',
        queryParameters: {'source': sourceId, 'series': seriesKey},
      );
      return Ok(OcrCoverage.fromJson(r.data!));
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<OcrSearchPage>> search(
    String query, {
    int limit = 20,
    int offset = 0,
  }) async {
    try {
      final r = await _dio.get<Map<String, dynamic>>(
        '/ocr/search',
        queryParameters: {'q': query, 'limit': limit, 'offset': offset},
      );
      return Ok(OcrSearchPage.fromJson(r.data!));
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
