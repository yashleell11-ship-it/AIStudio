import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/library/models/chapter.dart';
import 'package:aistudio_mobile/features/library/models/collection.dart';
import 'package:aistudio_mobile/features/library/models/collection_detail.dart';
import 'package:aistudio_mobile/features/library/models/continue_reading_item.dart';
import 'package:aistudio_mobile/features/library/models/reading_progress.dart';
import 'package:aistudio_mobile/features/library/models/library_statistics.dart';
import 'package:aistudio_mobile/features/library/models/reading_history_item.dart';
import 'package:aistudio_mobile/features/library/models/series_detail.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/features/library/models/tag.dart';
import 'package:aistudio_mobile/features/library/repositories/library_repository.dart';
import 'package:aistudio_mobile/features/reader/models/adjacent_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/bookmark.dart';
import 'package:dio/dio.dart';

class LibraryRepositoryImpl implements LibraryRepository {
  const LibraryRepositoryImpl(this._dio);

  final Dio _dio;

  @override
  Future<Result<PagedResult<SeriesSummary>>> listSeries({
    int page = 1,
    int perPage = 20,
    String? sort,
    String? search,
    String? status,
    String? readingStatus,
    int? collectionId,
    int? tagId,
    bool? isFavorite,
  }) =>
      _request(
        () => _dio.get<Map<String, dynamic>>(
          '/library/series',
          queryParameters: {
            'page': page,
            'per_page': perPage,
            if (sort != null) 'sort': sort,
            if (search != null) 'search': search,
            if (status != null) 'status': status,
            if (readingStatus != null) 'reading_status': readingStatus,
            if (collectionId != null) 'collection_id': collectionId,
            if (tagId != null) 'tag_id': tagId,
            if (isFavorite != null) 'is_favorite': isFavorite,
          },
        ),
        (data) => PagedResult.fromJson(data, SeriesSummary.fromJson),
      );

  @override
  Future<Result<SeriesDetail>> getSeries(int seriesId) => _request(
        () => _dio.get<Map<String, dynamic>>('/library/series/$seriesId'),
        SeriesDetail.fromJson,
      );

  @override
  Future<Result<ChapterDetail>> getChapter(int chapterId) => _request(
        () => _dio.get<Map<String, dynamic>>('/reader/chapter/$chapterId'),
        ChapterDetail.fromJson,
      );

  @override
  Future<Result<List<ContinueReadingItem>>> continueReading({int limit = 20}) =>
      _requestList(
        () => _dio.get<List<dynamic>>(
          '/library/continue-reading',
          queryParameters: {'limit': limit},
        ),
        ContinueReadingItem.fromJson,
      );

  @override
  Future<Result<List<SeriesSummary>>> recentlyAdded({int limit = 20}) =>
      _requestList(
        () => _dio.get<List<dynamic>>(
          '/library/recently-added',
          queryParameters: {'limit': limit},
        ),
        SeriesSummary.fromJson,
      );

  @override
  Future<Result<List<SeriesSummary>>> recentlyUpdated({int limit = 20}) =>
      _requestList(
        () => _dio.get<List<dynamic>>(
          '/library/recently-updated',
          queryParameters: {'limit': limit},
        ),
        SeriesSummary.fromJson,
      );

  @override
  Future<Result<List<SeriesSummary>>> recommendations({int limit = 20}) =>
      _requestList(
        () => _dio.get<List<dynamic>>(
          '/library/recommendations',
          queryParameters: {'limit': limit},
        ),
        SeriesSummary.fromJson,
      );

  @override
  Future<Result<List<SeriesSummary>>> search(String query, {int page = 1}) =>
      _request(
        () => _dio.get<Map<String, dynamic>>(
          '/library/search',
          queryParameters: {'q': query, 'page': page},
        ),
        (data) {
          final paged = PagedResult.fromJson(data, SeriesSummary.fromJson);
          return paged.items;
        },
      );

  @override
  Future<Result<ReadingProgress?>> getProgress(int seriesId) async {
    try {
      final response = await _dio.get<Map<String, dynamic>?>('/reader/progress/$seriesId');
      final data = response.data;
      return Ok(data != null ? ReadingProgress.fromJson(data) : null);
    } on DioException catch (e) {
      return Err(_extractError(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<ReadingProgress>> saveProgress({
    required int seriesId,
    required int chapterId,
    required int lastPage,
  }) =>
      _request(
        () => _dio.post<Map<String, dynamic>>(
          '/reader/progress',
          data: {
            'series_id': seriesId,
            'chapter_id': chapterId,
            'last_page': lastPage,
          },
        ),
        ReadingProgress.fromJson,
      );

  @override
  Future<Result<void>> deleteProgress(int seriesId) async {
    try {
      await _dio.delete<void>('/reader/progress/$seriesId');
      return const Ok(null);
    } on DioException catch (e) {
      return Err(_extractError(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<List<Collection>>> listCollections() => _requestList(
        () => _dio.get<List<dynamic>>('/library/collections'),
        Collection.fromJson,
      );

  @override
  Future<Result<CollectionDetail>> getCollection(int collectionId) => _request(
        () => _dio.get<Map<String, dynamic>>('/library/collections/$collectionId'),
        CollectionDetail.fromJson,
      );

  @override
  Future<Result<Collection>> createCollection({
    required String name,
    String? description,
  }) =>
      _request(
        () => _dio.post<Map<String, dynamic>>(
          '/library/collections',
          data: {
            'name': name,
            if (description != null && description.isNotEmpty) 'description': description,
          },
        ),
        Collection.fromJson,
      );

  @override
  Future<Result<Collection>> updateCollection(
    int collectionId, {
    String? name,
    String? description,
  }) =>
      _request(
        () => _dio.patch<Map<String, dynamic>>(
          '/library/collections/$collectionId',
          data: {
            if (name != null) 'name': name,
            if (description != null) 'description': description,
          },
        ),
        Collection.fromJson,
      );

  @override
  Future<Result<void>> deleteCollection(int collectionId) async {
    try {
      await _dio.delete<void>('/library/collections/$collectionId');
      return const Ok(null);
    } on DioException catch (e) {
      return Err(_extractError(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<void>> addSeriesToCollection(int collectionId, int seriesId) async {
    try {
      await _dio.post<void>('/library/collections/$collectionId/series/$seriesId');
      return const Ok(null);
    } on DioException catch (e) {
      return Err(_extractError(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<void>> removeSeriesFromCollection(
    int collectionId,
    int seriesId,
  ) async {
    try {
      await _dio.delete<void>(
        '/library/collections/$collectionId/series/$seriesId',
      );
      return const Ok(null);
    } on DioException catch (e) {
      return Err(_extractError(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<List<Tag>>> listTags() => _requestList(
        () => _dio.get<List<dynamic>>('/library/tags'),
        Tag.fromJson,
      );

  @override
  Future<Result<void>> toggleFavorite(int seriesId) async {
    try {
      await _dio.post<void>('/library/series/$seriesId/favorite');
      return const Ok(null);
    } on DioException catch (e) {
      return Err(_extractError(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  @override
  Future<Result<LibraryStatistics>> statistics() => _request(
        () => _dio.get<Map<String, dynamic>>('/library/statistics'),
        LibraryStatistics.fromJson,
      );

  @override
  Future<Result<List<ReadingHistoryItem>>> readingHistory({int limit = 50}) =>
      _requestList(
        () => _dio.get<List<dynamic>>(
          '/library/reading-history',
          queryParameters: {'limit': limit},
        ),
        ReadingHistoryItem.fromJson,
      );

  @override
  Future<Result<List<ReadingCalendarDay>>> readingCalendar({int days = 30}) =>
      _requestList(
        () => _dio.get<List<dynamic>>(
          '/library/reading-calendar',
          queryParameters: {'days': days},
        ),
        ReadingCalendarDay.fromJson,
      );

  @override
  Future<Result<Bookmark>> addBookmark({
    required int seriesId,
    required int chapterId,
    required int page,
    String? note,
  }) =>
      _request(
        () => _dio.post<Map<String, dynamic>>(
          '/reader/bookmarks',
          data: {
            'series_id': seriesId,
            'chapter_id': chapterId,
            'page': page,
            if (note != null) 'note': note,
          },
        ),
        Bookmark.fromJson,
      );

  @override
  Future<Result<AdjacentChapter?>> getAdjacentChapter(
    int chapterId, {
    required String direction,
  }) async {
    try {
      final response = await _dio.get<Map<String, dynamic>?>(
        '/reader/chapter/$chapterId/adjacent',
        queryParameters: {'direction': direction},
      );
      final data = response.data;
      return Ok(data != null ? AdjacentChapter.fromJson(data) : null);
    } on DioException catch (e) {
      return Err(_extractError(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  Future<Result<T>> _request<T>(
    Future<Response<Map<String, dynamic>>> Function() call,
    T Function(Map<String, dynamic>) fromJson,
  ) async {
    try {
      final response = await call();
      return Ok(fromJson(response.data!));
    } on DioException catch (e) {
      return Err(_extractError(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  Future<Result<List<T>>> _requestList<T>(
    Future<Response<List<dynamic>>> Function() call,
    T Function(Map<String, dynamic>) fromJson,
  ) async {
    try {
      final response = await call();
      final items = (response.data ?? [])
          .map((e) => fromJson(e as Map<String, dynamic>))
          .toList();
      return Ok(items);
    } on DioException catch (e) {
      return Err(_extractError(e));
    } catch (e) {
      return Err(UnknownError(message: e.toString(), cause: e));
    }
  }

  AppError _extractError(DioException e) {
    if (e.error is AppError) return e.error! as AppError;
    return UnknownError(message: e.message ?? 'Dio error', cause: e);
  }
}
