import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/reader/models/reader_chapter.dart';
import 'package:aistudio_mobile/features/sources/models/source.dart';
import 'package:aistudio_mobile/features/sources/models/source_series.dart';
import 'package:aistudio_mobile/features/sources/repositories/sources_repository.dart';
import 'package:dio/dio.dart';

class SourcesRepositoryImpl implements SourcesRepository {
  SourcesRepositoryImpl(this._dio, this._apiBaseUrl);

  final Dio _dio;
  final String _apiBaseUrl;

  @override
  Future<Result<List<SourceSummary>>> listSources() async {
    try {
      final r = await _dio.get<List<dynamic>>('/sources');
      final items = (r.data ?? [])
          .map((e) => SourceSummary.fromJson(e as Map<String, dynamic>))
          .toList();
      return Ok(items);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<List<SourceBrowseMode>>> listBrowseModes(String sourceId) async {
    try {
      final r = await _dio.get<List<dynamic>>('/sources/$sourceId/browse-modes');
      final items = (r.data ?? [])
          .map((e) => SourceBrowseMode.fromJson(e as Map<String, dynamic>))
          .toList();
      return Ok(items);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<PagedResult<SourceSeriesSummary>>> listSeries(
    String sourceId, {
    int page = 1,
    String? query,
    String? sort,
  }) async {
    try {
      final r = await _dio.get<Map<String, dynamic>>(
        '/sources/$sourceId/series',
        queryParameters: {
          'page': page,
          if (query != null) 'query': query,
          if (sort != null) 'sort': sort,
        },
      );
      final paged = PagedResult<SourceSeriesSummary>(
        items: (r.data!['items'] as List<dynamic>)
            .map(
              (e) => SourceSeriesSummary.fromJson(
                e as Map<String, dynamic>,
                _apiBaseUrl,
              ),
            )
            .toList(),
        total: r.data!['total'] as int,
        page: r.data!['page'] as int,
        perPage: r.data!['page_size'] as int,
        hasNext: r.data!['has_more'] as bool,
      );
      return Ok(paged);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<SourceSeriesSummary>> getSeries(
    String sourceId,
    String seriesId,
  ) async {
    try {
      final r = await _dio.get<Map<String, dynamic>>(
        '/sources/$sourceId/series/$seriesId',
      );
      return Ok(SourceSeriesSummary.fromJson(r.data!, _apiBaseUrl));
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<List<SourceChapterSummary>>> getChapters(
    String sourceId,
    String seriesId,
  ) async {
    try {
      final r = await _dio.get<List<dynamic>>(
        '/sources/$sourceId/series/$seriesId/chapters',
      );
      final items = (r.data ?? [])
          .map((e) => SourceChapterSummary.fromJson(e as Map<String, dynamic>))
          .toList();
      return Ok(items);
    } on DioException catch (e) {
      return Err(_err(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<ReaderChapter>> getReaderChapter(
    String sourceId,
    String seriesId,
    String chapterId,
  ) async {
    try {
      // chapterId is appended raw so slash-bearing ids (e.g. toonily's
      // ``series/chapter-1``) match the backend ``:path`` route converter.
      final r = await _dio.get<Map<String, dynamic>>(
        '/sources/$sourceId/series/$seriesId/chapters/$chapterId/reader',
      );
      return Ok(ReaderChapter.fromJson(r.data!, _apiBaseUrl));
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
