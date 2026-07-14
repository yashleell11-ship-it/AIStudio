"""Connector branding helpers — site favicons for the sources grid."""

from __future__ import annotations

import importlib

from connectors.base import SourceConnector

# Hand-crafted connectors whose favicon does not live on their API host.
_SITE_ORIGINS: dict[str, str] = {
    "asurascans": "https://asuracomic.net",
    "asura": "https://asuracomic.net",
    "mangadex": "https://mangadex.org",
    "aurorascans": "https://qimanga.com",
    "beehentai": "https://beehentai.com",
    "comicland": "https://comicland.org",
    "asmhentai": "https://asmhentai.com",
    "threehentai": "https://3hentai.net",
    "nhentai": "https://nhentai.net",
    "ehentai": "https://e-hentai.org",
    "bbato": "https://bato.to",
    "doujins": "https://doujins.com",
}


def _site_base_for(connector_cls: type[SourceConnector]) -> str | None:
    config = getattr(connector_cls, "CONFIG", None)
    if config is not None:
        return str(config.base_url).rstrip("/")

    site_base = getattr(connector_cls, "SITE_BASE", None)
    if site_base:
        return str(site_base).rstrip("/")

    module_name = connector_cls.__module__
    if module_name.endswith(".connector"):
        mappers_name = f"{module_name.rsplit('.', 1)[0]}.mappers"
        try:
            mappers = importlib.import_module(mappers_name)
        except ImportError:
            mappers = None
        if mappers is not None:
            site_base = getattr(mappers, "SITE_BASE", None)
            if site_base:
                return str(site_base).rstrip("/")

    origin = getattr(connector_cls, "SITE_ORIGIN", None) or _SITE_ORIGINS.get(
        connector_cls.SOURCE_TYPE
    )
    return origin.rstrip("/") if origin else None


def connector_icon_url(connector_cls: type[SourceConnector]) -> str | None:
    """Best-effort favicon URL for a connector's public site."""
    site_base = _site_base_for(connector_cls)
    if site_base:
        return f"{site_base}/favicon.ico"
    return None
