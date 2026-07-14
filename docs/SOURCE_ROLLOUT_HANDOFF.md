# Source Connector Rollout — Full Handoff

Use this doc when switching Cursor accounts or handing off the ManhwaManiacs source-fixing project.

**Cursor rule (auto-loaded):** `.cursor/rules/source-connector-rollout.mdc`

**Live site:** https://manhwamaniacs.xyz  
**Repo:** `/home/yash/dev/aistudio` · **Branch:** `develop`

---

## 1. What we're doing

Fix every source in the **Sources** grid so users can:

1. **Browse** — catalog loads (no 502, no infinite skeletons)
2. **Series** — metadata + cover
3. **Chapters** — chapter list
4. **Reader** — page images load via proxy

Work **one source at a time**, top-to-bottom in the grid. **Deploy production backend after each fix.** User verifies in UI before moving on.

---

## 2. Infrastructure & deploy

### Docker production stack

```bash
cd /home/yash/dev/aistudio
docker compose -p manhwamaniacs-production build backend
docker compose -p manhwamaniacs-production up -d backend
```

- **Frontend:** `manhwamaniacs-production` (port 3000, Caddy edge)
- **Backend:** `manhwamaniacs-production-backend` (internal :8000)
- **Data volume:** SQLite + settings at `/data/` in backend container
- **Settings:** `/data/settings.json` — `mature_content_enabled` must be `true` for 18+ sources

### Verify connector in production

```bash
docker exec manhwamaniacs-production-backend python -c "
from connectors.registry import create_connector
from services.browse_service import BrowseService
sid = 'SOURCE_ID'
c = create_connector(sid)
listing = c.get_series_list(1)
print(type(c).__name__, len(listing.items), listing.items[0].title if listing.items else 'EMPTY')
svc = BrowseService()
out = svc.list_series(sid, page=1, sort='latest')
print('browse_service', len(out['items']))
"
```

### Probe external sites from production

```bash
docker exec manhwamaniacs-production-backend python -c "
from curl_cffi.requests import Session
import re
s = Session(impersonate='chrome131')
r = s.get('https://DOMAIN/', timeout=20, allow_redirects=True)
print(r.status_code, r.url, len(r.text))
print('madara', 'page-item-detail' in r.text.lower())
"
```

### Run tests

```bash
cd backend && python -m pytest tests/test_SOURCE_connector.py -q
```

---

## 3. Architecture

### Connector types

| Type | Where | When |
|------|-------|------|
| **Madara factory** | `MADARA_CATALOG` in `catalog.py` → `madara/factory.py` | Site has Madara WordPress theme (`page-item-detail`, `/manga/` or `/serie/`) |
| **Handcrafted** | `backend/connectors/<name>/` | Custom HTML, API, or non-Madara structure |
| **Excluded** | `excluded.py` | Dead domain, CF JS wall, parked — hidden from registry |

### Registration checklist (custom connector)

1. Create `backend/connectors/<id>/` — `connector.py`, `mappers.py`, `__init__.py`
2. Remove `_site("<id>", ...)` from `MADARA_CATALOG` in `catalog.py` (if present)
3. Add `"<id>"` to `HANDCRAFTED_CONNECTORS` in `catalog.py`
4. Import + register in `registry.py` `_register_builtin_connectors()` **before** Madara classes
5. Add to `_CONFIGLESS_CONNECTORS` in `registry.py`
6. Add `tests/test_<id>_connector.py` + `tests/fixtures/<id>/`
7. Deploy backend

### Key backend files

| File | Role |
|------|------|
| `connectors/catalog.py` | All Madara site configs + `HANDCRAFTED_CONNECTORS` + `MADARA_LIVE` |
| `connectors/registry.py` | Connector registration & `create_connector()` |
| `connectors/excluded.py` | `EXCLUDED_CONNECTORS` — skipped at registration |
| `connectors/madara/connector.py` | Generic Madara browse/read |
| `connectors/madara/config.py` | `url_segment` (manga/serie/custom), `use_cf`, `mature` |
| `connectors/http/client.py` | `SyncConnectorHttpClient` (httpx) |
| `connectors/http/ddg_client.py` | `DdgSyncHttpClient` (curl_cffi) — CF/DDoS-Guard/API 403 |
| `services/browse_service.py` | API facade; maps `ConnectorHttpError` → 502 |
| `routes/sources.py` | `/sources/{id}/series`, covers, pages, reader |

### Key frontend files

| File | Role |
|------|------|
| `features/sources/components/SourceBrowserView.tsx` | Browse UI, sort tabs, genre, search |
| `features/sources/components/SourceSeriesGrid.tsx` | Grid / skeleton / error states |
| `features/sources/hooks.ts` | `useInfiniteSourceSeries` react-query |
| `features/sources/api.ts` | HTTP calls to `/sources/...` |

### UI error symptoms

| Symptom | Likely cause |
|---------|--------------|
| "Could not load source catalog" + 502 | Connector HTTP failure (wrong URL, dead site) |
| Infinite gray skeleton cards | Slow Madara retries (~9s) or hung request |
| Empty grid, no error | Zero results (wrong parser) |
| 404 on source | Mature content disabled or excluded |

---

## 4. Fix patterns (learned this session)

### Madara config tweaks

```python
# Wrong segment — AllPornComic
_site("allporncomic", "AllPornComic", "allporncomic.com", url_segment="porncomic", mature=True, use_cf=False)

# ToonGod uses serie not manga
_site("toongod", "ToonGod", "toongod.org", url_segment="serie", mature=True)
```

### CDN / image proxy

- Some CDNs 403 without browser TLS or Referer
- **Akuma pattern:** `DdgSyncHttpClient` + `fetch_proxied_image()` on connector
- **Cover route:** `/sources/{id}/series/{series_id:path}/cover` — no rate limit on covers

### Dead / blocked sources → exclude

```python
# backend/connectors/excluded.py
EXCLUDED_CONNECTORS = frozenset({
    "comick",
    "allhenscan",      # NXDOMAIN
    "1stkissmanga",    # parked
    "asiatoon",        # Cloudflare JS challenge
})
```

### Domain redirects

Always probe with `allow_redirects=True` and use **final URL** for connector:

| Catalog domain | Actual site | Connector |
|---------------|-------------|-----------|
| aurorascans.com | qimanga.com | `aurorascans/` EZManhwa API |
| asmhentai.com | asmhentai.com | NOT Madara — `/g/{id}/` galleries |

### API needs curl_cffi

QiManga API (`api.qimanga.com`) returns **403 on httpx**, **200 on curl_cffi** with `Origin` + `Referer` headers. Use `DdgSyncHttpClient.get_json()`.

---

## 5. Completed sources (session log)

| # | Source ID | Display | Solution | Notes |
|---|-----------|---------|----------|-------|
| 1 | `18porncomic` | 18PornComic | Custom `porncomic18/` | WordPress comic theme |
| 2 | `1stkissmanga` | 1st Kiss Manga | **EXCLUDED** | Parked / Cheq protection |
| 3 | `3hentai` | 3Hentai | Custom `threehentai/` | HTML nhentai-style |
| 4 | `8muses` | 8Muses | Custom `eightmuses/` | Cover cache + browse covers |
| 5 | `akuma` | Akuma | Custom `akuma/` | `DdgSyncHttpClient` for `s*.akuma.moe` |
| 6 | `allhenscan` | AllHenScan | **EXCLUDED** | NXDOMAIN |
| 7 | `allporncomic` | AllPornComic | Madara `url_segment="porncomic"` | |
| 8 | `apcomics` | APComics | Madara (works) | User confirmed |
| 9 | `asiatoon` | AsiaToon | **EXCLUDED** | CF JS challenge |
| 10 | `asmhentai` | AsmHentai | Custom `asmhentai/` | `/g/{id}/`, `/gallery/{id}/{n}/`, `images.asmhentai.com` |
| 11 | `asurascans` | AsuraScans | Pre-existing handcrafted | User confirmed working |
| 12 | `aurorascans` | Aurora Scans | Custom `aurorascans/` | Redirects to qimanga.com; API `api.qimanga.com/api/v1` |

### Pre-existing handcrafted (not fixed this session)

`mangadex`, `mangakatana`, `demonicscans`, `toonily`, `coffeemanga`, `nhentai`

---

## 6. Next sources (catalog order after Aurora Scans)

Continue from **BaoZiMH** downward in `MADARA_CATALOG`:

| Source ID | Domain | Probe notes (stale — re-probe!) |
|-----------|--------|--------------------------------|
| `baozimh` | baozimh.com | CUSTOM_NEEDED per probe |
| `bato` | bato.to | Timeout / unreachable |
| `bbato` | bbato.com | 404 on /serie/ |
| `beehentai` | beehentai.com | 404 |
| `cartoonmad` | cartoonmad.com | DEAD |
| `cmanhua` | cmanhua.com | 404 |
| `cocomic` | cocomic.co | Madara LIVE |
| `coffeemanga` | (custom) | Already handcrafted LIVE |
| ... | | See `docs/CONNECTOR_STATUS.md` |

**~150+ Madara catalog entries total.** Don't batch-fix — one deploy per source.

---

## 7. Cursor / Claude prompts

> **Claude (product/platform):** use [`docs/CLAUDE_HANDOFF.md`](CLAUDE_HANDOFF.md) — connectors are frozen; do not touch `backend/connectors/`.

### Main continuation prompt (Cursor only — connectors)

```
Continue fixing ManhwaManiacs sources one-by-one, top-to-bottom in the Sources grid.

Read first:
- docs/SOURCE_ROLLOUT_HANDOFF.md
- .cursor/rules/source-connector-rollout.mdc

Repo: /home/yash/dev/aistudio, branch develop.
Deploy after each fix: docker compose -p manhwamaniacs-production build backend && docker compose -p manhwamaniacs-production up -d backend

Next source: BaoZiMH (baozimh.com).

For each source:
1. Probe from production container (curl_cffi)
2. Decide: Madara tweak, custom connector, or exclude
3. Implement + tests
4. Deploy + verify get_series_list returns items
5. Tell user to verify browse → series → chapters → reader in UI

Do not commit unless I ask.
```

### Per-source investigation prompt

```
Fix source SOURCE_ID (DOMAIN) for ManhwaManiacs.

Symptom: [502 / stuck skeletons / empty grid / covers broken / reader 403]

Steps:
1. docker exec manhwamaniacs-production-backend — probe DOMAIN with curl_cffi
2. Check if Madara (page-item-detail, /manga/, /serie/) or custom
3. Check redirects (final URL may differ from catalog domain)
4. Fix: catalog config / custom connector / excluded.py
5. tests/test_SOURCE_connector.py + fixtures
6. Deploy production backend
7. Verify: create_connector('SOURCE_ID').get_series_list(1) returns N>0

Reference connectors: asurascans (API), threehentai (HTML), aurorascans (EZManhwa API), akuma (DdgSyncHttpClient).
```

### Deploy-only prompt

```
Deploy the current backend to manhwamaniacs production and verify SOURCE_ID loads 20+ series:

cd /home/yash/dev/aistudio
docker compose -p manhwamaniacs-production build backend
docker compose -p manhwamaniacs-production up -d backend
# then docker exec verify script
```

### Exclude dead source prompt

```
Source SOURCE_ID is dead/unreachable (NXDOMAIN / CF wall / parked).
Add to backend/connectors/excluded.py, ensure it's removed from active Madara catalog if needed, deploy backend. User should no longer see it in Sources grid (or not get 502).
```

---

## 8. Handcrafted connector templates

### Minimal file layout

```
backend/connectors/SOURCE_ID/
  __init__.py          # export Connector class
  connector.py         # SourceConnector subclass
  mappers.py           # parse API/HTML → Series, Chapter, Page

backend/tests/
  test_SOURCE_ID_connector.py
  fixtures/SOURCE_ID/
    series_list.json   # or .html
    series_detail.json
    chapter_list.json
    chapter_pages.json
```

### registry.py additions

```python
from connectors.SOURCE_ID.connector import SourceConnectorClass

# In _CONFIGLESS_CONNECTORS:
SourceConnectorClass.SOURCE_TYPE,

# In _register_builtin_connectors builtins tuple (BEFORE Madara classes):
(SourceConnectorClass.SOURCE_TYPE, SourceConnectorClass),
```

### catalog.py

```python
# Remove from MADARA_CATALOG:
# _site("source_id", ...),

# Add to HANDCRAFTED_CONNECTORS:
HANDCRAFTED_CONNECTORS = frozenset({
    ..., "source_id",
})
```

---

## 9. Probe scripts (maintenance)

```bash
cd backend
python scripts/probe_catalog_domains.py --retry-dead
python scripts/probe_all_connectors.py --retry-dead
python scripts/generate_connector_status.py   # refreshes docs/CONNECTOR_STATUS.md
```

Probe JSON snapshots: `docs/catalog_domain_probe.json`, `docs/connector_probe_results.json`

---

## 10. Session infrastructure added

| Addition | Purpose |
|----------|---------|
| `excluded.py` | Hide dead sources from registry |
| `madara/config.py` custom `url_segment` | Non-manga paths (porncomic, serie) |
| `browse_service.py` error mapping | Connector errors → 502 `source_unreachable` |
| `base.py` `fetch_proxied_image()` | CDN image override hook |
| `ddg_client.py` `get_json()` | JSON API via curl_cffi |
| `SourceSeriesGrid.tsx` | Show errors before skeletons |
| `sources.py` cover `{series_id:path}` | Slug paths with slashes |

---

## 11. Git / commits

- **Do not commit** unless user explicitly asks
- User verifies each source in UI before moving on
- Production deploys are local docker compose (not necessarily CI)

---

## 12. Quick reference — connector packages

| Package | Source ID | Type |
|---------|-----------|------|
| `asurascans/` | asurascans | REST API |
| `mangadex/` | mangadex | MangaDex API |
| `mangakatana/` | mangakatana | HTML scrape |
| `demonicscans/` | demonicscans | Custom |
| `toonily/` | toonily | Madara-like custom |
| `coffeemanga/` | coffeemanga | Custom |
| `nhentai/` | nhentai | nhentai API v2 |
| `porncomic18/` | 18porncomic | WordPress |
| `threehentai/` | 3hentai | HTML gallery |
| `eightmuses/` | 8muses | WordPress |
| `akuma/` | akuma | Laravel + Ddg CDN |
| `asmhentai/` | asmhentai | HTML gallery |
| `aurorascans/` | aurorascans | QiManga EZManhwa API |
| `firstkissmanga/` | 1stkissmanga | Custom (excluded) |
| `madara/` | 140+ sites | Factory from catalog |

---

*Last updated: 2026-07-11 — through Aurora Scans fix. Next: BaoZiMH.*
