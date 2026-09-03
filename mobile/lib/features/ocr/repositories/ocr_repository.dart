import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/ocr/models/ocr_coverage.dart';
import 'package:manhwamaniacs/features/ocr/models/ocr_search_result.dart';
import 'package:manhwamaniacs/features/ocr/models/page_text.dart';

/// The four `/ocr/*` endpoints (spec §4). Identity is the same opaque
/// `(sourceId, seriesKey, chapterKey)` triple as everywhere else.
abstract interface class OcrRepository {
  /// `POST /ocr/chapter`. [pages] must already satisfy the ingest bounds —
  /// `capOcrPagesForUpload` is the one place that guarantees it, and the
  /// implementation calls it rather than trusting callers.
  ///
  /// Returns the stored transcript's word count, which is how a caller knows
  /// the server actually took the upload: the ingest service silently keeps
  /// an existing transcript when the incoming one is empty.
  Future<Result<int>> uploadChapter({
    required ChapterIdentity id,
    required List<PageText> pages,
    required String engine,
    double? chapterNumber,
    String? language,
  });

  /// `GET /ocr/coverage` — the stored word count per chapter of one series.
  Future<Result<OcrCoverage>> coverage({
    required String sourceId,
    required String seriesKey,
  });

  /// `GET /ocr/search` — dialogue search, already scoped server-side to the
  /// caller's followed series and 18+ gate.
  Future<Result<OcrSearchPage>> search(
    String query, {
    int limit = 20,
    int offset = 0,
  });
}
