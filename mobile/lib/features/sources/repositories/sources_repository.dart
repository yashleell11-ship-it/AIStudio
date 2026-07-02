import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/reader/models/reader_chapter.dart';
import 'package:aistudio_mobile/features/sources/models/source.dart';
import 'package:aistudio_mobile/features/sources/models/source_series.dart';

abstract interface class SourcesRepository {
  Future<Result<List<SourceSummary>>> listSources();

  Future<Result<List<SourceBrowseMode>>> listBrowseModes(String sourceId);

  Future<Result<PagedResult<SourceSeriesSummary>>> listSeries(
    String sourceId, {
    int page = 1,
    String? query,
    String? sort,
  });

  Future<Result<SourceSeriesSummary>> getSeries(String sourceId, String seriesId);

  Future<Result<List<SourceChapterSummary>>> getChapters(
    String sourceId,
    String seriesId,
  );

  /// Unified reader payload for an online chapter (pages + adjacent chapter
  /// ids). Hits ``GET /sources/{sourceId}/series/{seriesId}/chapters/{chapterId}/reader``.
  Future<Result<ReaderChapter>> getReaderChapter(
    String sourceId,
    String seriesId,
    String chapterId,
  );
}
