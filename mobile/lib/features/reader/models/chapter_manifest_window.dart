import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';

/// One `POST /reader/chapters/manifest` answer — the download plans for a
/// bounded WINDOW of one series' chapters, fetched in a single round trip.
///
/// Downloading a 300-chapter series one manifest at a time is 300 requests
/// before a single page is on disk, and 300 chapter-list scrapes upstream on a
/// cold cache. Naive pipelining of those is also what earned this app a real,
/// minutes-long 429 from a source, which is the failure this window exists to
/// avoid — the bulk endpoint has its own much tighter bucket precisely so a
/// client can ask for twenty at once instead of racing twenty requests.
///
/// The server answers per item: exactly one of `manifest`/`error` is non-null
/// for each key, so one bad chapter in a window of twenty costs that chapter
/// and nothing else. That is why this splits into two maps rather than
/// throwing.
class ChapterManifestWindow {
  const ChapterManifestWindow({
    required this.maxChapters,
    required this.manifests,
    required this.errors,
  });

  /// The server's own stride, echoed on every success so a download paces
  /// itself by the cap the deployment actually has rather than by a number
  /// compiled into the app. Over it is a 413, so this is the one number worth
  /// believing.
  final int maxChapters;

  /// The manifests that came back, by the `chapter_key` the request asked for
  /// — never by the key inside the payload, so a connector that normalises its
  /// own keys cannot silently orphan a queued row.
  final Map<String, ChapterManifest> manifests;

  /// Per-chapter failures, by requested key. Present so the caller can tell
  /// "the window did not include it" from "the window said it is broken"; both
  /// fall back to the single-chapter path, which owns the retry bound.
  final Map<String, String> errors;

  factory ChapterManifestWindow.fromJson(Map<String, dynamic> json) {
    final manifests = <String, ChapterManifest>{};
    final errors = <String, String>{};
    for (final raw in (json['items'] as List<dynamic>? ?? const [])) {
      if (raw is! Map) continue;
      final item = Map<String, dynamic>.from(raw);
      final key = item['chapter_key'] as String?;
      if (key == null || key.isEmpty) continue;
      final payload = item['manifest'];
      if (item['status'] == 'ok' && payload is Map) {
        final manifest =
            ChapterManifest.fromJson(Map<String, dynamic>.from(payload));
        // A chapter with no pages is not a chapter. Recording it as an error
        // keeps it on the single path, where the queue's own "no pages"
        // failure and retry bound already live.
        if (manifest.pageCount <= 0 || manifest.pages.isEmpty) {
          errors[key] = 'This chapter has no pages.';
        } else {
          manifests[key] = manifest;
        }
        continue;
      }
      final error = item['error'];
      errors[key] = error is Map && error['message'] is String
          ? error['message'] as String
          : 'This chapter could not be fetched.';
    }
    return ChapterManifestWindow(
      maxChapters: (json['max_chapters'] as num?)?.toInt() ?? 0,
      manifests: manifests,
      errors: errors,
    );
  }
}
