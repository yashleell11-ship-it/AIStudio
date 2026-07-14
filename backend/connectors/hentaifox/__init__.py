"""HentaiFox online source connector."""

from __future__ import annotations

from connectors.hentaifamily.connector import build_hentai_family_connector
from connectors.hentaifamily.mappers import HentaiFamilySite

HENTAIFOX_SITE = HentaiFamilySite(
    source_id="hentaifox",
    display_name="HentaiFox",
    site_base="https://hentaifox.com",
    reader_segment="g",
    image_host_suffix="hentaifox.com",
)

HentaiFoxConnector = build_hentai_family_connector(HENTAIFOX_SITE)

__all__ = ["HentaiFoxConnector", "HENTAIFOX_SITE"]
