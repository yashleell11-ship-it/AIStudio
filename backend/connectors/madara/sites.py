"""Madara-theme site registration."""

from __future__ import annotations

from connectors.catalog import MADARA_CATALOG, MADARA_LIVE

# Rollout phase: register the full catalog (155) so probes can attempt every source.
# Production deploys may filter to ``MADARA_LIVE`` until custom connectors land.
MADARA_SITES: tuple = MADARA_CATALOG

# Confirmed-live subset for ``rebuild_live_sites.py`` / production pruning.
MADARA_LIVE_IDS = MADARA_LIVE
