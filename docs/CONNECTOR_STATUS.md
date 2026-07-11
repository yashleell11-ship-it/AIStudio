# Connector rollout tracker

| Status | Meaning |
|--------|---------|
| `LIVE` | Verified browse returns series (2026-07-11 mass probe) |
| `DEAD` | Removed from registry after 3-strike / empty listing |
| `SKIPPED` | Never registered (Comick excluded permanently) |

## Mass live probe (2026-07-11)

Script: `backend/scripts/probe_all_connectors.py`  
Results: `docs/connector_probe_results.json`

**155 probed → 21 LIVE → 134 pruned**

### Hand-crafted (always registered)

| ID | Status |
|----|--------|
| mangadex | LIVE |
| asurascans | LIVE |
| mangakatana | LIVE |
| demonicscans | LIVE |
| toonily | LIVE (18+, requires mature setting) |
| coffeemanga | LIVE |

### Madara factory (live-probed only)

| ID | Sample title | Mature |
|----|--------------|--------|
| manhuaplus | Magic Emperor | no |
| mangaread | My Older Sister Is a Sword Saint… | no |
| manhuakey | I Got Pregnant with Him… | no |
| manhuanext | The Yellow-Haired Villain… | yes |
| manhuahot | The Hunter's Gonna Lay Low | yes |
| topmanhua | The Shepherd Wizard | yes |
| manhwaclub | Rooftop Sex King | yes |
| manhwatop | Mood Disorder | yes |
| manhwaden | Greedy | yes |
| manhwanex | Devil Summoner… | yes |
| apcomics | Shuuko vs Tadano-kun | yes |
| cocomic | Tyrant of the Otherworld Prison… | yes |
| cucumbermanga | PEARL BOY… | yes |
| manga18x | It's A Lie, But It's Okay | yes |
| pawmanga | Falling in Love Gives Me Superpowers | yes |

### Excluded permanently

- **Comick** — product decision, never register.

### Re-probe

```bash
cd backend && .venv/bin/python scripts/probe_all_connectors.py
```
