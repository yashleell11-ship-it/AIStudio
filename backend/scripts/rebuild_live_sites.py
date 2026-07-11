#!/usr/bin/env python3
"""Rebuild madara/sites.py keeping only LIVE probed sources."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SITES_PY = REPO / "backend" / "connectors" / "madara" / "sites.py"
RESULTS = REPO / "docs" / "connector_probe_results.json"
HANDCRAFTED = frozenset(
    {"mangadex", "asurascans", "mangakatana", "demonicscans", "toonily", "coffeemanga"}
)


def _header(probed_date: str, live_count: int, hc_count: int) -> str:
    return f'''"""Madara-theme site catalog — live-probed entries only."""

from __future__ import annotations

from connectors.madara.config import MadaraSiteConfig


def _site(
    source_id: str,
    display_name: str,
    domain: str,
    *,
    url_segment: str = "manga",
    mature: bool = False,
    use_cf: bool = True,
    extra_image_hosts: frozenset[str] = frozenset(),
) -> MadaraSiteConfig:
    return MadaraSiteConfig(
        source_id=source_id,
        display_name=display_name,
        base_url=f"https://{{domain}}",
        url_segment=url_segment,
        mature=mature,
        use_cf=use_cf,
        extra_image_hosts=extra_image_hosts,
    )


# fmt: off
# Live-probed {probed_date}: {live_count} Madara sources (+ {hc_count} hand-crafted).
MADARA_SITES: tuple[MadaraSiteConfig, ...] = (
'''


def main() -> None:
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    live_ids = {
        r["source_id"]
        for r in data["results"]
        if r["status"] == "LIVE" and r["source_id"] not in HANDCRAFTED
    }

    text = SITES_PY.read_text(encoding="utf-8")
    site_lines: list[str] = []
    for line in text.splitlines():
        m = re.match(r'^(\s*)_site\("([^"]+)"', line)
        if m and m.group(2) in live_ids and not line.lstrip().startswith("#"):
            site_lines.append(f"    {line.lstrip()}")

    if not site_lines:
        raise SystemExit("No matching _site lines found for live IDs")

    body = _header(data["probed_at"][:10], len(site_lines), len(HANDCRAFTED))
    footer = ")\n# fmt: on\n"
    SITES_PY.write_text(body + "\n".join(site_lines) + "\n" + footer, encoding="utf-8")
    print(f"Rebuilt sites.py with {len(site_lines)} live Madara entries")


if __name__ == "__main__":
    main()
