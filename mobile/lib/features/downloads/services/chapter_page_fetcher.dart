import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// Fetches one manifest page's raw bytes. Split out from [DownloadQueueController]
/// so tests can inject a failing/controlled fetcher (mocktail) instead of a
/// real Dio — the same seam the offline-reader acceptance test uses to
/// simulate airplane mode without a real network.
abstract class ChapterPageFetcher {
  Future<List<int>> fetchPageBytes(String url);
}

class DioChapterPageFetcher implements ChapterPageFetcher {
  DioChapterPageFetcher(this._dio);

  final Dio _dio;

  @override
  Future<List<int>> fetchPageBytes(String url) async {
    final response = await _dio.get<List<int>>(
      url,
      options: Options(responseType: ResponseType.bytes),
    );
    return response.data ?? const [];
  }
}

/// Shares the app's single Dio client — the reader page proxy needs the same
/// bearer token and `X-Profile-Id` header every other API call carries (kept
/// in sync by `profileHeaderSyncProvider`), so nothing here attaches auth
/// itself.
final chapterPageFetcherProvider = Provider<ChapterPageFetcher>(
  (ref) => DioChapterPageFetcher(ref.watch(dioProvider)),
  name: 'chapterPageFetcher',
);
