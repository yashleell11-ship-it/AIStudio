/// Client-side per-chapter reading progress for online source chapters.
///
/// Online-source chapters have no server-side progress model, so the app
/// persists a small record locally. The shape is a shared cross-platform
/// contract — the web client persists the identical shape, keyed by
/// `sourceId:seriesId:chapterId`:
///
/// ```json
/// { "page": 3, "pageCount": 20, "completed": false, "updatedAt": "2026-07-12T…Z" }
/// ```
class SourceChapterProgress {
  const SourceChapterProgress({
    required this.page,
    required this.pageCount,
    required this.completed,
    required this.updatedAt,
  });

  /// 1-based current page.
  final int page;

  /// Total pages in the chapter (0 when unknown).
  final int pageCount;

  /// ``true`` once [page] reaches [pageCount] (with ``pageCount > 0``).
  final bool completed;

  /// Last time this record was written (UTC).
  final DateTime updatedAt;

  factory SourceChapterProgress.fromJson(Map<String, dynamic> json) {
    final parsedUpdatedAt =
        DateTime.tryParse(json['updatedAt'] as String? ?? '')?.toUtc();
    return SourceChapterProgress(
      page: (json['page'] as num?)?.toInt() ?? 1,
      pageCount: (json['pageCount'] as num?)?.toInt() ?? 0,
      completed: json['completed'] as bool? ?? false,
      updatedAt:
          parsedUpdatedAt ?? DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
    );
  }

  Map<String, dynamic> toJson() => {
        'page': page,
        'pageCount': pageCount,
        'completed': completed,
        'updatedAt': updatedAt.toUtc().toIso8601String(),
      };
}
