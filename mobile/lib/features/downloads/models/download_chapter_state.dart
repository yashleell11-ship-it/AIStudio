/// Lifecycle of a chapter in the on-device store.
///
/// A chapter is only ever [complete] once every one of its pages has a row in
/// `saved_pages` — there is no partial-complete state, so a kill mid-chapter
/// (app closed, OS eviction) always leaves it at [queued] or [downloading],
/// resumable by re-entering the queue and skipping pages already present.
enum DownloadChapterState {
  /// Waiting for the queue to reach it. Also the state a [failed] or
  /// interrupted chapter returns to on manual retry.
  queued,

  /// Actively fetching pages, or was doing so when the app last stopped —
  /// downloads are foreground-only, so "downloading" found at launch just
  /// means "resume this".
  downloading,

  /// Every page is present on disk. The only state a page count/bytes total
  /// is trusted to be final.
  complete,

  /// Bounded retries were exhausted for this chapter. Surfaced in the
  /// Downloads screen with a retry action — never silently dropped.
  failed;

  bool get isTerminal => this == complete || this == failed;

  static DownloadChapterState fromWire(String value) => switch (value) {
        'queued' => DownloadChapterState.queued,
        'downloading' => DownloadChapterState.downloading,
        'complete' => DownloadChapterState.complete,
        'failed' => DownloadChapterState.failed,
        _ => DownloadChapterState.queued,
      };

  String get wire => name;
}
