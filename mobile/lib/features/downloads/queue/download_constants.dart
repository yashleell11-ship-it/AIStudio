/// The non-negotiable free-space floor (spec §3/§3b): the queue stops dead
/// once free space on the store's volume drops below this, independent of
/// any user-configured cap. ~1.5 GB.
const int kFreeSpaceFloorBytes = 1536 * 1024 * 1024;

/// Pages fetched at once per chapter — a deliberate cap, not "as fast as
/// possible": the reader endpoints sit behind the per-request auth gate
/// (`docs/OFFLINE_READING.md` §1), so unbounded concurrency turns one
/// chapter download into a burst of SQLite write contention on the backend.
///
/// Fixed, and deliberately NOT a second user setting next to
/// [DownloadConcurrency]: two multiplying knobs is how a user arrives at a
/// number neither of them looks like. Chapter parallelism is the one that is
/// exposed; this one stays where the auth gate put it.
const int kPageFetchConcurrency = 2;

/// The hard ceiling on requests the download queue has open against the
/// user's server at once — manifests, novel text and page images together,
/// across *every* chapter in flight.
///
/// This is the number that actually bounds the blast radius, and the reason
/// [DownloadConcurrency] can be offered at all. Without it the real
/// concurrency would be the product (3 chapters x [kPageFetchConcurrency] = 6
/// and climbing with the setting); with it, the worst case is four whatever
/// the user picks, so raising the setting overlaps dead time — manifest round
/// trips, retry backoffs, blob writes — rather than multiplying the request
/// rate.
///
/// Four, not more: `services/bulk_fetch.py` is the backend's own answer to
/// "how much concurrent upstream work does this box want", and it sizes its
/// pool at 4 by default with a hard `MAX_CONCURRENCY = 16` — "the box has
/// 2 vCPU and these threads each hold an upstream socket". Page-image proxying
/// is exactly that shape of work. Four is also inside the shape of the
/// `sources` rate-limit bucket the page proxy is charged to, which the
/// serial queue was already pressing against.
///
/// Per-source politeness is not this constant's job and does not need to be:
/// everything that scrapes a source's own site resolves through the ONE cached
/// connector instance per source, whose `min_interval` is held under a lock
/// (`backend/connectors/registry.py`), so fanning out across a single source
/// is spaced upstream by the server no matter what this app does. Page bytes
/// come from CDNs on a pooled client with no such spacing — which is precisely
/// why they need a ceiling here.
const int kQueueRequestConcurrency = 4;

/// Consecutive manifest-fetch failures before a chapter is marked
/// [DownloadChapterState.failed] rather than retried again on this pass.
const int kMaxChapterManifestRetries = 3;

/// Consecutive failures for a single page before its chapter is marked
/// failed. Deliberately small — one truly broken page (a source's proxy
/// 404ing that page) should not stall the whole download for minutes.
const int kMaxPageRetries = 3;

const Duration kChapterRetryBackoff = Duration(seconds: 2);
const Duration kPageRetryBackoff = Duration(milliseconds: 600);

/// How many novel chapters one `POST /novels/chapters` window asks for
/// before the server has said otherwise.
///
/// Matches the deployed `MM_NOVEL_BULK_MAX_CHAPTERS`, but is only a starting
/// guess: every successful window echoes `max_chapters`, and the queue adopts
/// that number, so a deployment that raises or lowers its cap needs no app
/// release. Over the cap is a `batch_too_large` 413, which the queue also
/// reads and shrinks to.
const int kNovelWindowChapters = 20;

/// Below this, a window is not worth asking for: the single-chapter endpoint
/// sits on a far more generous rate-limit bucket than the `bulk` one, so
/// spending a bulk token on one chapter is a straight loss.
const int kMinNovelWindowChapters = 2;

/// How many chapters one `POST /reader/chapters/manifest` window asks for
/// before the server has said otherwise.
///
/// Its own constant rather than a shared one with [kNovelWindowChapters]: the
/// two endpoints are sized by two different settings server-side
/// (`MM_READER_BULK_MAX_CHAPTERS` / `MM_NOVEL_BULK_MAX_CHAPTERS`), and a
/// deployment is free to move one without the other. As with novels this is
/// only a starting guess — every successful window echoes `max_chapters` and
/// the queue adopts it, and over the cap is a `batch_too_large` 413 the queue
/// also reads and shrinks to.
const int kManifestWindowChapters = 20;

/// Below this, a manifest window is not worth asking for: the single-chapter
/// endpoint sits on a far more generous rate-limit bucket than the `bulk` one,
/// so spending a bulk token on one chapter is a straight loss.
const int kMinManifestWindowChapters = 2;

/// How long the queue leaves the `bulk` bucket alone after a window call comes
/// back useless.
///
/// One duration for both window endpoints because the server charges them to
/// ONE bucket (`core/rate_limit.py`'s `bulk_limit` covers
/// `POST /reader/chapters/manifest` and `POST /novels/chapters` alike), so a
/// refusal earned by either has to rest both. Without it a queue whose windows
/// keep failing asks for a fresh window per chapter — strictly more requests
/// than the per-chapter path it replaces, aimed at the tightest bucket we
/// have, which is exactly the shape that drew a real multi-minute 429 before.
const Duration kBulkWindowCooldown = Duration(seconds: 30);
