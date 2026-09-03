/// The non-negotiable free-space floor (spec §3/§3b): the queue stops dead
/// once free space on the store's volume drops below this, independent of
/// any user-configured cap. ~1.5 GB.
const int kFreeSpaceFloorBytes = 1536 * 1024 * 1024;

/// Pages fetched at once per chapter — a deliberate cap, not "as fast as
/// possible": the reader endpoints sit behind the per-request auth gate
/// (`docs/OFFLINE_READING.md` §1), so unbounded concurrency turns one
/// chapter download into a burst of SQLite write contention on the backend.
const int kPageFetchConcurrency = 2;

/// Consecutive manifest-fetch failures before a chapter is marked
/// [DownloadChapterState.failed] rather than retried again on this pass.
const int kMaxChapterManifestRetries = 3;

/// Consecutive failures for a single page before its chapter is marked
/// failed. Deliberately small — one truly broken page (a source's proxy
/// 404ing that page) should not stall the whole download for minutes.
const int kMaxPageRetries = 3;

const Duration kChapterRetryBackoff = Duration(seconds: 2);
const Duration kPageRetryBackoff = Duration(milliseconds: 600);
