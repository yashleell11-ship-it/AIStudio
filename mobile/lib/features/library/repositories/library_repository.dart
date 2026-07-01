import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/library/models/chapter.dart';
import 'package:aistudio_mobile/features/library/models/collection.dart';
import 'package:aistudio_mobile/features/library/models/continue_reading_item.dart';
import 'package:aistudio_mobile/features/library/models/reading_progress.dart';
import 'package:aistudio_mobile/features/library/models/library_statistics.dart';
import 'package:aistudio_mobile/features/library/models/series_detail.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/features/library/models/tag.dart';
import 'package:aistudio_mobile/features/reader/models/adjacent_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/bookmark.dart';

abstract interface class LibraryRepository {
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
  });

  Future<Result<SeriesDetail>> getSeries(int seriesId);

  Future<Result<ChapterDetail>> getChapter(int chapterId);

  Future<Result<List<ContinueReadingItem>>> continueReading({int limit = 20});

  Future<Result<List<SeriesSummary>>> recentlyAdded({int limit = 20});

  Future<Result<List<SeriesSummary>>> recentlyUpdated({int limit = 20});

  Future<Result<List<SeriesSummary>>> recommendations({int limit = 20});

  Future<Result<List<SeriesSummary>>> search(String query, {int page = 1});

  Future<Result<ReadingProgress?>> getProgress(int seriesId);

  Future<Result<ReadingProgress>> saveProgress({
    required int seriesId,
    required int chapterId,
    required int lastPage,
  });

  Future<Result<void>> deleteProgress(int seriesId);

  Future<Result<List<Collection>>> listCollections();

  Future<Result<List<Tag>>> listTags();

  Future<Result<void>> toggleFavorite(int seriesId);

  Future<Result<LibraryStatistics>> statistics();

  Future<Result<Bookmark>> addBookmark({
    required int seriesId,
    required int chapterId,
    required int page,
    String? note,
  });

  Future<Result<AdjacentChapter?>> getAdjacentChapter(
    int chapterId, {
    required String direction,
  });
}
