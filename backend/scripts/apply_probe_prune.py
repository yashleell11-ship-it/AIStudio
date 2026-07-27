#!/usr/bin/env python3
"""Comment out DEAD/ERROR Madara sites in catalog.py from probe results."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CATALOG_PY = REPO / "backend" / "connectors" / "catalog.py"
RESULTS = REPO / "docs" / "connector_probe_results.json"

HANDCRAFTED = frozenset(
    {"mangadex", "asurascans", "mangakatana", "demonicscans", "toonily", "coffeemanga"}
)


def main() -> None:
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    dead_ids = {
        r["source_id"]
        for r in data["results"]
        if r["status"] in ("DEAD", "ERROR") and r["source_id"] not in HANDCRAFTED
    }
    live_ids = {r["source_id"] for r in data["results"] if r["status"] == "LIVE"}

    text = CATALOG_PY.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    changed = 0

    for line in lines:
        m = re.match(r'^(\s*)_site\("([^"]+)"', line)
        if m and m.group(2) in dead_ids and not line.lstrip().startswith("#"):
            indent = m.group(1)
            out.append(f"{indent}# Probed DEAD {data['probed_at'][:10]}: {m.group(2)}\n")
            out.append(f"{indent}# {line.lstrip()}")
            changed += 1
            continue
        out.append(line)

    CATALOG_PY.write_text("".join(out), encoding="utf-8")
    print(f"Commented out {changed} dead Madara entries")
    print(f"Live: {len(live_ids)} | Dead pruned: {len(dead_ids)}")


if __name__ == "__main__":
    main()
