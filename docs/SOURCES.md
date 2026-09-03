# ManhwaManiacs Source System

ManhwaManiacs supports pluggable **source connectors** for browsing and reading
online catalogs, similar to Mihon/Tachiyomi. The rest of the application never
depends on a specific website — only on normalized connector data and the
opaque `(source_id, series_key, chapter_key)` identity every connector's keys
are treated as (see [ARCHITECTURE.md](ARCHITECTURE.md)). There is no local
catalog any more: every series a user reads comes from a live connector, and
`series_key`/`chapter_key` are that connector's own strings, stored and passed
through raw — never parsed.

## Architecture

```
connectors/          ~50 connector packages (mangadex, asurascans, toonily, a
                      Madara-site factory config, ...) + registry.py, base.py
services/             browse_service, reader_service, source_cache_service,
                      source_pin_service
routes/sources.py     HTTP API for browsing + online reading (the image proxy)
routes/reader.py      GET /reader/chapter/manifest — the source-agnostic
                       reader payload built from a connector's chapter/page list
frontend/src/app/sources/       Sources UI (browse, search, per-source series)
frontend/src/app/reader/        Chapter reader
```

## Connector interface

Every connector implements `SourceConnector` in `backend/connectors/base.py`:

| Method | Purpose |
|--------|---------|
| `get_series_list(page, *, sort=None)` | Paginated catalog browse |
| `search_series(query, page, *, sort=None)` | Search within the source |
| `get_series(series_id)` | Series metadata |
| `get_chapters(series_id)` | Chapter list |
| `get_chapter_pages(chapter_id)` | Page list, each with a `remote_url` |

`series_id`/`chapter_id` here are the connector's own opaque strings, not
database ids. Connectors return normalized models from `connectors/models.py`
(`Series`, `Chapter`, `Page`, `PaginatedSeriesList`) — the rest of the app
never branches on which connector produced them.

A connector also declares `is_mature` (hides it from Sources and search unless
`Settings.mature_content_enabled` is on) and `allowed_image_hosts` (the SSRF
allowlist the image proxy enforces — see `BrowseService._fetch_url`).

## Installed connectors

`backend/connectors/registry.py` currently registers on the order of 50
connectors — most hand-written (MangaDex against its official API, Toonily
behind Cloudflare via `curl_cffi`, and similar), plus a larger set generated
from a shared "Madara" WordPress-theme factory config
(`connectors/catalog.py` + `connectors/madara/factory.py`) for sites that all
speak the same HTML shape. Registered but **not browsable**:
`local_filesystem` — a leftover from the deleted local-import feature (no
route calls it any more; nothing to register a folder against). The exact
live list drifts as sources go up/down — check `registry.py` or `GET /sources`
rather than trusting a hardcoded table here.

Register a new connector by adding it to `connectors/registry.py`:

```python
from connectors.registry import register_connector

register_connector("mysite", MySiteConnector)
```

## HTTP API

| Endpoint | Description |
|----------|-------------|
| `GET /sources` | List browsable connectors |
| `GET /sources/search?query=` | Federated search across sources |
| `GET /sources/{id}/series?query=&page=&sort=` | Browse or search one source |
| `GET /sources/{id}/series/{series_key:path}` | Series detail |
| `GET /sources/{id}/series/{series_key:path}/chapters` | Chapter list |
| `GET /sources/{id}/series/{series_key:path}/cover` | Proxied cover image |
| `GET /sources/{id}/series/{series_key:path}/chapters/{chapter_key:path}/reader` | Reader payload for one chapter |
| `GET /sources/{id}/pages/{page_key:path}/image` | Proxied page image — the one byte source both online reading and on-device downloads use |
| `GET /reader/chapter/manifest?source=&series=&chapter=` | The download/read plan: ordered page list + prev/next chapter keys |

`series_key`/`chapter_key`/`page_key` path segments are `:path`-typed because
they can contain slashes; encode them per segment (the web client's
`encodePathKey` is the reference) rather than concatenating raw strings into a
URL.

## Reading flow

1. A user opens a chapter from **Sources**, or from their library
   (`followed_series` — see [ARCHITECTURE.md](ARCHITECTURE.md)) at
   `/reader/{sourceId}/{seriesKey}/{chapterKey}`.
2. The client fetches `GET /reader/chapter/manifest?source=&series=&chapter=`
   for the ordered page list, then loads each page through
   `GET /sources/{source}/pages/{page:path}/image`.
3. Nothing is cached server-side. Web caches into browser Cache Storage via a
   service worker if the reader chooses to keep it offline; mobile writes into
   its on-device sqflite + blob store. Both read the exact same proxy URLs the
   live reader uses.

## Adding another connector

1. Create `connectors/{name}/connector.py` implementing `SourceConnector`.
2. Use `connectors/http/client.py` for HTTP, retries, and rate limiting if the
   site needs bespoke handling; if it's a Madara-themed site, add it to
   `connectors/catalog.py` instead and skip writing a connector at all.
3. Map API/HTML responses to normalized models in a local `mappers.py`.
4. Register it in `connectors/registry.py`.
5. No frontend or route changes required — the UI only depends on the
   normalized models and the generic `/sources/*` endpoints.
