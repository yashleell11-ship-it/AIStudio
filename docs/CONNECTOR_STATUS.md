# Connector rollout tracker

| Status | Meaning |
|--------|---------|
| `LIVE` | Domain returns parseable connector HTML |
| `DEAD` | Unreachable or wrong stack after 3 probe attempts |
| `REGISTERED` | In registry; not yet probed |
| `SKIPPED` | Removed from registry |

## Hand-crafted (always on)

| ID | Domain | Status |
|----|--------|--------|
| mangadex | mangadex.org | LIVE |
| asurascans | asuracomic.net | LIVE |
| mangakatana | mangakatana.com | LIVE |
| demonicscans | demonicscans.org | LIVE |
| toonily | toonily.com | LIVE (18+) |
| coffeemanga | coffeemanga.ink | LIVE |

## Live probe batch 1 (2026-07-11)

Script: `backend/scripts/gen_madara_live_fixtures.py`

| Source ID | Domain | Status | Notes |
|-----------|--------|--------|-------|
| manhuaplus | manhuaplus.com | **LIVE** | Madara HTML; fixtures in `tests/fixtures/madara/manhuaplus/` |
| manganato | natomanga.com | DEAD | CF 403 on `/manga/` |
| readmanganato | readmanganato.com | DEAD | JS SPA shell |
| mangabat | mangabat.com | DEAD | Parked redirect |
| mangafire | mangafire.to | DEAD | Custom SPA, not Madara |
| zinmanga | zinmanga.com | DEAD | Anti-bot redirect |
| flamescans | flamecomics.xyz | DEAD | Next.js `/browse`, not Madara |

**DEAD entries removed from `madara/sites.py` registry** (commented in source).

## Madara factory

~155 sites registered via `connectors/madara/sites.py` (minus confirmed DEAD).
Most are **REGISTERED** until probed. Re-run:

```bash
cd backend && . .venv/bin/activate && python scripts/gen_madara_live_fixtures.py
```

**Excluded permanently:** Comick / comick.io

**Reality check:** Many registered sites use non-Madara stacks (hentai indexes,
official apps, SPAs). They need dedicated connector templates or removal after probe.
