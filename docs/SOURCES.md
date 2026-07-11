# ManhwaManiacs Source System

ManhwaManiacs supports pluggable **source connectors** for browsing and reading online catalogs, similar to Mihon/Tachiyomi. The rest of the application never depends on a specific website — only on normalized connector data.

## Architecture

```
connectors/          Plugin implementations (mangadex, asurascans, mangakatana,
                     demonicscans, toonily, local_filesystem)
services/            browse_service, reading_service, source_service
routes/sources.py    HTTP API for browsing and online reading
features/sources/    Frontend Sources UI (no source-specific logic)
features/reader/     Unified chapter reader (local + online)
```

## Connector interface

Every connector implements `SourceConnector` in `backend/connectors/base.py`:

| Method | Purpose |
|--------|---------|
| `get_series_list(page)` | Paginated catalog browse |
| `search_series(query, page)` | Search within the source |
| `get_series(series_id)` | Series metadata |
| `get_chapters(series_id)` | Chapter list |
| `get_chapter_pages(chapter_id)` | Page list with `remote_url` or local paths |
| `find_page(page_id)` | Optional efficient page lookup |

Connectors return normalized models from `connectors/models.py`:

- **Series** — title, author, artist, status, genres, cover_url, latest_chapter
- **Chapter** — title, number, page_count
- **Page** — number, remote_url or file_path

## Installed connectors

| ID | Type | Browsable | Import |
|----|------|-----------|--------|
| `mangadex` | MangaDex official API | Yes | No |
| `asurascans` | AsuraScans (HTML catalog) | Yes | No |
| `mangakatana` | MangaKatana (HTML catalog) | Yes | No |
| `demonicscans` | DemonicScans (HTML catalog) | Yes | No |
| `toonily` | Toonily (HTML catalog; Cloudflare-hardened via curl_cffi) | Yes | No |
| `local_filesystem` | Folder scan | No | Yes |

Register new connectors in `connectors/registry.py`:

```python
from connectors.registry import register_connector

register_connector("mangadex", MangaDexConnector)
```

## MangaDex connector

Located at `connectors/mangadex/`. Uses the official MangaDex API with:

- Async HTTP client (`connectors/http/client.py`) behind the sync connector API
- Retries on transient failures (408, 429, 5xx)
- 30s timeouts
- ~4.8 requests/second rate limiting
- TTL metadata caches (series, chapters, at-home page URLs)
- Image URLs proxied through ManhwaManiacs (required by MangaDex hotlink policy)

## HTTP API

| Endpoint | Description |
|----------|-------------|
| `GET /sources` | List browsable connectors |
| `GET /sources/{id}/series?query=&page=` | Browse or search series |
| `GET /sources/{id}/series/{series_id}` | Series detail |
| `GET /sources/{id}/series/{series_id}/chapters` | Chapter list |
| `GET /sources/{id}/series/{series_id}/cover` | Proxied cover image |
| `GET /sources/{id}/series/{series_id}/chapters/{chapter_id}/reader` | Unified reader payload |
| `GET /sources/{id}/pages/{page_id}/image` | Proxied page image |

## Reading flow

1. User opens a chapter from **Sources** → `/reader/online/{sourceId}/{seriesId}/{chapterId}`
2. Backend `ReadingService.resolve_source_chapter()` checks for a local downloaded copy (future)
3. If no local copy, returns remote pages with proxied `image_url` values
4. `ChapterReader` renders the same continuous scroll UI for local and online content

## Frontend routes

| Route | Purpose |
|-------|---------|
| `/sources` | Installed connectors |
| `/sources/{sourceId}` | Searchable series grid |
| `/sources/{sourceId}/series/{seriesId}` | Series detail + chapter list |
| `/reader/online/...` | Online chapter reader |

## Adding another connector

1. Create `connectors/{name}/connector.py` implementing `SourceConnector`
2. Use `connectors/http/client.py` for HTTP, retries, and rate limits
3. Map API responses to normalized models in a local `mappers.py`
4. Register in `connectors/registry.py`
5. No frontend or route changes required

## Local library

The existing local import flow is unchanged:

`POST /library/import` → `SourceService` → `LocalFilesystemConnector` → SQLite

Local library and online sources remain separate until download / add-to-library is implemented.
