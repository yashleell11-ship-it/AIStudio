import 'package:manhwamaniacs/features/novels/models/novel_chapter.dart';

/// One `POST /novels/chapters` answer — a bounded WINDOW of a book's chapters
/// fetched in a single round trip (spec R5).
///
/// A novel chapter is a few kilobytes of prose, so downloading a 300-chapter
/// book one request at a time is almost entirely round-trip overhead. The
/// server answers per item: exactly one of `chapter`/`error` is non-null for
/// each key, so one bad chapter in a window of twenty costs that chapter and
/// nothing else. That is why this splits into two maps rather than throwing.
class NovelChapterWindow {
  const NovelChapterWindow({
    required this.maxChapters,
    required this.chapters,
    required this.errors,
  });

  /// The server's own stride, echoed on every success so a download paces
  /// itself by the cap the deployment actually has rather than by a number
  /// compiled into the app. Over it is a 413, so this is the one number worth
  /// believing.
  final int maxChapters;

  /// The chapters that came back, by the `chapter_key` the request asked for
  /// — never by the key inside the payload, so a connector that normalises
  /// its own keys cannot silently orphan a queued row.
  final Map<String, NovelChapter> chapters;

  /// Per-chapter failures, by requested key. Present so the caller can tell
  /// "the window did not include it" from "the window said it is broken";
  /// both fall back to the single-chapter path, which owns the retry bound.
  final Map<String, String> errors;

  factory NovelChapterWindow.fromJson(Map<String, dynamic> json) {
    final chapters = <String, NovelChapter>{};
    final errors = <String, String>{};
    for (final raw in (json['items'] as List<dynamic>? ?? const [])) {
      if (raw is! Map) continue;
      final item = Map<String, dynamic>.from(raw);
      final key = item['chapter_key'] as String?;
      if (key == null || key.isEmpty) continue;
      final payload = item['chapter'];
      if (item['status'] == 'ok' && payload is Map) {
        final chapter =
            NovelChapter.fromJson(Map<String, dynamic>.from(payload));
        // A chapter with no prose is not a chapter. Recording it as an error
        // keeps it on the single path, where the queue's own "no text"
        // failure and retry bound already live.
        if (chapter.paragraphs.isEmpty) {
          errors[key] = 'This chapter has no text.';
        } else {
          chapters[key] = chapter;
        }
        continue;
      }
      final error = item['error'];
      errors[key] = error is Map && error['message'] is String
          ? error['message'] as String
          : 'This chapter could not be fetched.';
    }
    return NovelChapterWindow(
      maxChapters: (json['max_chapters'] as num?)?.toInt() ?? 0,
      chapters: chapters,
      errors: errors,
    );
  }
}
