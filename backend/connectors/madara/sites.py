"""Madara-theme site registration — live-probed production subset."""

from __future__ import annotations

from connectors.catalog import MADARA_CATALOG, MADARA_LIVE

# Production: only register connectors confirmed live by probe (2026-07-11).
MADARA_SITES: tuple = tuple(
    cfg for cfg in MADARA_CATALOG if cfg.source_id in MADARA_LIVE
)
