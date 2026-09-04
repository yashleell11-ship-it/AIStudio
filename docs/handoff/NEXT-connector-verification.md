# Connector verification and cleanup, then 2.1.0

Owner's instruction (2026-09-05): *"make sure those all work from the inside and all
must made a custom conectors for every connnector if they doesnt work then speed up
if are ded remove the are update 2.1.0 not 2.0.0"*

## 1. Verify from the inside, not by probing

Every source must be exercised **through the app's own service layer**, not by fetching
a homepage. A 200 on `/` proves nothing — several sources in this repo have served a
homepage happily while their chapter images 404'd.

Per source, on the VPS (`ssh -o BatchMode=yes ubuntu@135.148.43.147`, then
`docker exec manhwamaniacs-backend python ...` so it runs on production's TLS stack and
egress IP), through the registry and connector classes themselves:

1. `get_series_list` — a browse/listing page returns series
2. `search_series` — a real query returns results
3. `get_series` — detail resolves for one of those series
4. `get_chapters` — a chapter list comes back, with usable `chapter_number`s
5. `get_chapter_pages` — page URLs resolve
6. **the page bytes actually download and are images** — this is the stage that
   distinguishes "listed" from "readable", and it is the one that matters to the owner
7. For novel sources: `chapter_text` returns sanitized English paragraphs

Record per-stage latency, not just pass/fail. A source that works in nine seconds is a
source the owner experiences as broken.

## 2. Then act on the result

- **Works and fast** — leave alone.
- **Works but slow** — optimise. Known shapes already fixed in this repo: fetching the
  series page twice (share one fetch via a TTL cache, see `royalroad`), ignoring a
  one-shot chapter-list endpoint, a request per page for image resolution, no connection
  pooling.
- **Broken but fixable** — fix. Usual causes: moved CDN host, required browser UA on
  image GETs, markup change, relative-vs-absolute URLs, a dead `exc.status_code == 404`
  check (`SyncConnectorHttpClient` only sets `status_code` for RETRYABLE_STATUS).
- **Dead** — deregister and delete. A source that only ever errors is worse than an
  absent one: it costs the owner a tap and a wait to discover the same failure again.

## 3. On "a custom connector for every connector"

Four sources are Madara-theme entries served by the shared factory
(`connectors/madara/`) rather than bespoke modules. That is not a shortcut — it is one
tested implementation with per-site config, and forking it into four near-identical
copies would multiply the maintenance surface without adding capability.

**The test is behaviour, not file count**: if a Madara-catalog site fails any stage in
§1 *because* the shared implementation does not fit it, it gets its own connector. If it
passes every stage, it stays on the factory. Same bar as everything else.

## 4. Version

The release is **2.1.0**. Note `frontend/package.json` was set to 2.0.0 by an agent —
that is a private scaffold field nothing reads, but correct it anyway. The version the
clients actually report is `mobile/pubspec.yaml` (currently `1.14.0+28`), and the
backend changelog entry in `backend/routes/app_distribution.py`.
