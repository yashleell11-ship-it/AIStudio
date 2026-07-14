"""HentaiEra online source connector."""

from __future__ import annotations

from connectors.hentaifamily.connector import build_hentai_family_connector
from connectors.hentaifamily.mappers import HentaiFamilySite

HENTAIERA_SITE = HentaiFamilySite(
    source_id="hentaiera",
    display_name="HentaiEra",
    site_base="https://hentaiera.com",
    reader_segment="view",
    image_host_suffix="hentaiera.com",
)

HentaiEraConnector = build_hentai_family_connector(HENTAIERA_SITE)

__all__ = ["HentaiEraConnector", "HENTAIERA_SITE"]
