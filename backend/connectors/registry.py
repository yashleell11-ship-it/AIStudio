"""Registry for pluggable source connectors."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from connectors.akuma.connector import AkumaConnector
from connectors.asmhentai.connector import AsmHentaiConnector
from connectors.aurorascans.connector import AuroraScansConnector
from connectors.bbato.connector import BbatoConnector
from connectors.beehentai.connector import BeeHentaiConnector
from connectors.comicland.connector import ComicLandConnector
from connectors.flamescans.connector import FlameScansConnector
from connectors.freeadultcomix.connector import FreeAdultComixConnector
from connectors.baozimh.connector import BaoZiMHConnector
from connectors.cmanhua.connector import CManhuaConnector
from connectors.comicasura.connector import ComicAsuraConnector
from connectors.comicsvalley.connector import ComicsValleyConnector
from connectors.ehentai.connector import EHentaiConnector
from connectors.elftoon.connector import ElfToonConnector
from connectors.galaxymanga.connector import GalaxyMangaConnector
from connectors.harimanga.connector import HariMangaConnector
from connectors.hentai20.connector import Hentai20Connector
from connectors.hentaifox import HentaiFoxConnector
from connectors.hentaiera import HentaiEraConnector
from connectors.asurascans.connector import AsuraScansConnector
from connectors.base import SourceConnector
from connectors.branding import connector_icon_url
from core.config import get_settings
from connectors.coffeemanga.connector import CoffeeMangaConnector
from connectors.eightmuses.connector import EightMusesConnector
from connectors.local_filesystem.connector import LocalFilesystemConnector
from connectors.excluded import EXCLUDED_CONNECTORS
from connectors.madara.factory import madara_connector_classes
from connectors.madara.sites import MADARA_SITES
from connectors.mangabuddy.connector import MangaBuddyConnector
from connectors.mangafreak.connector import MangaFreakConnector
from connectors.mangadex.connector import MangaDexConnector
from connectors.mangahub.connector import MangaHubConnector
from connectors.mangapill.connector import MangaPillConnector
from connectors.mangatown.connector import MangaTownConnector
from connectors.manhwa18.connector import Manhwa18Connector
from connectors.novelcool.connector import NovelCoolConnector
from connectors.omegascans.connector import OmegaScansConnector
from connectors.rawinu.connector import RawInuConnector
from connectors.rawkuma.connector import RawkumaConnector
from connectors.archiveorg.connector import ArchiveOrgConnector
from connectors.freewebnovel.connector import FreeWebNovelConnector
from connectors.gutenberg.connector import GutenbergConnector
from connectors.novelbuddy.connector import NovelBuddyConnector
from connectors.novelarchive.connector import NovelArchiveConnector
from connectors.novelfull.connector import NovelFullConnector
from connectors.royalroad.connector import RoyalRoadConnector
from connectors.standardebooks.connector import StandardEbooksConnector
from connectors.mangakatana.connector import MangaKatanaConnector
from connectors.demonicscans.connector import DemonicScansConnector
from connectors.doujins.connector import DoujinsConnector
from connectors.fanfox.connector import FanFoxConnector
from connectors.firstkissmanga.connector import FirstKissMangaConnector
from connectors.nhentai.connector import NHentaiConnector
from connectors.porncomic18.connector import PornComic18Connector
from connectors.threehentai.connector import ThreeHentaiConnector
from connectors.toonily.connector import ToonilyConnector
from connectors.webtoons.connector import WebtoonsConnector
from connectors.tapas.connector import TapasConnector
from connectors.weebcentral.connector import WeebCentralConnector

logger = logging.getLogger(__name__)

REQUIRED_BROWSABLE_CONNECTORS = frozenset({"asurascans", "mangadex"})

_MADARA_CONNECTOR_CLASSES: tuple[type[SourceConnector], ...] = tuple(
    madara_connector_classes(MADARA_SITES)
)

_CONFIGLESS_CONNECTORS: set[str] = {
    AkumaConnector.SOURCE_TYPE,
    AsuraScansConnector.SOURCE_TYPE,
    CoffeeMangaConnector.SOURCE_TYPE,
    MangaDexConnector.SOURCE_TYPE,
    MangaKatanaConnector.SOURCE_TYPE,
    MangaBuddyConnector.SOURCE_TYPE,
    MangaPillConnector.SOURCE_TYPE,
    MangaHubConnector.SOURCE_TYPE,
    MangaFreakConnector.SOURCE_TYPE,
    MangaTownConnector.SOURCE_TYPE,
    Manhwa18Connector.SOURCE_TYPE,
    NovelCoolConnector.SOURCE_TYPE,
    OmegaScansConnector.SOURCE_TYPE,
    RawInuConnector.SOURCE_TYPE,
    RawkumaConnector.SOURCE_TYPE,
    FanFoxConnector.SOURCE_TYPE,
    DemonicScansConnector.SOURCE_TYPE,
    DoujinsConnector.SOURCE_TYPE,
    ToonilyConnector.SOURCE_TYPE,
    NHentaiConnector.SOURCE_TYPE,
    PornComic18Connector.SOURCE_TYPE,
    ThreeHentaiConnector.SOURCE_TYPE,
    AsmHentaiConnector.SOURCE_TYPE,
    AuroraScansConnector.SOURCE_TYPE,
    BbatoConnector.SOURCE_TYPE,
    BeeHentaiConnector.SOURCE_TYPE,
    ComicLandConnector.SOURCE_TYPE,
    FlameScansConnector.SOURCE_TYPE,
    FreeAdultComixConnector.SOURCE_TYPE,
    BaoZiMHConnector.SOURCE_TYPE,
    CManhuaConnector.SOURCE_TYPE,
    ComicAsuraConnector.SOURCE_TYPE,
    ComicsValleyConnector.SOURCE_TYPE,
    EHentaiConnector.SOURCE_TYPE,
    ElfToonConnector.SOURCE_TYPE,
    GalaxyMangaConnector.SOURCE_TYPE,
    Hentai20Connector.SOURCE_TYPE,
    HentaiFoxConnector.SOURCE_TYPE,
    HentaiEraConnector.SOURCE_TYPE,
    HariMangaConnector.SOURCE_TYPE,
    EightMusesConnector.SOURCE_TYPE,
    TapasConnector.SOURCE_TYPE,
    FirstKissMangaConnector.SOURCE_TYPE,
    ArchiveOrgConnector.SOURCE_TYPE,
    FreeWebNovelConnector.SOURCE_TYPE,

    GutenbergConnector.SOURCE_TYPE,

    NovelBuddyConnector.SOURCE_TYPE,
    NovelArchiveConnector.SOURCE_TYPE,
    NovelFullConnector.SOURCE_TYPE,
    RoyalRoadConnector.SOURCE_TYPE,
    StandardEbooksConnector.SOURCE_TYPE,
    # Both take no constructor arguments and hold exactly the state this set
    # exists to keep alive -- a pooled keep-alive HTTP client, its per-site
    # rate lock, and several TTL caches. Leaving them out built all of that
    # fresh on every call and threw it away: no connection reuse, TTL caches
    # that never hit, and (the one that bites) no SHARED min_interval, so
    # concurrent reads of one of these sources were not spaced at all. That
    # last part is what the bulk chapter windows rely on for politeness.
    WebtoonsConnector.SOURCE_TYPE,
    WeebCentralConnector.SOURCE_TYPE,
    *(cls.SOURCE_TYPE for cls in _MADARA_CONNECTOR_CLASSES),
}

_INSTANCE_CACHE: dict[str, SourceConnector] = {}


class ConnectorRegistrationError(RuntimeError):
    """Raised when a required connector fails to register."""


@dataclass(frozen=True, slots=True)
class ConnectorDescriptor:
    """Metadata for an installed connector."""

    source_type: str
    name: str
    description: str
    browsable: bool
    supports_import: bool
    mature: bool = False
    icon_url: str | None = None
    # "manga" (default) or "novel" — clients branch on it to open the right
    # reader (spec 2026-09-04-novels-design §3).
    content_kind: str = "manga"
    # BCP-47-ish language of the source's content ("en"), None when unknown.
    # Novel connectors are English-only by decree and set LANGUAGE = "en";
    # existing manga connectors carry no declaration and stay None.
    language: str | None = None


def _novels_enabled() -> bool:
    """The MM_NOVELS_ENABLED gate, read at CALL time, not import time.

    Production must remain a manhwa site while the flag is off (spec
    2026-09-04-novels-design §2): novel connector classes stay in the static
    ``_REGISTRY`` (imports are unconditional and cheap), but every query
    surface below — listing, instantiation, type enumeration — filters them
    out when the flag is off, so from anywhere outside this module an
    unflagged deployment genuinely does not have them: ``GET /sources`` never
    lists them and ``create_connector`` refuses them exactly like an unknown
    source type (404 upstream). Reading the flag per call keeps both states
    testable in one process; the env var itself only changes on restart.
    """
    return bool(getattr(get_settings(), "novels_enabled", False))


def _is_novel_class(connector_cls: type[SourceConnector]) -> bool:
    return getattr(connector_cls, "CONTENT_KIND", "manga") == "novel"


_REGISTRY: dict[str, type[SourceConnector]] = {}


def register_connector(source_type: str, connector_cls: type[SourceConnector]) -> None:
    """Register a connector class under a stable source type key."""
    if not source_type:
        raise ConnectorRegistrationError("Connector source_type must not be empty.")
    if not issubclass(connector_cls, SourceConnector):
        raise ConnectorRegistrationError(
            f"Connector '{source_type}' must subclass SourceConnector."
        )
    _REGISTRY[source_type] = connector_cls


# Connectors that exist under connectors/ but are deliberately NOT registered,
# because each one reaches a backend an already-registered source already
# reaches. Verified from the production container by asking both connectors
# for the same catalog and comparing what came back -- not by comparing
# domain names, which is exactly what makes these look like distinct sites.
#
#   flamecomics -> flamescans   Both read flamecomics.xyz. Identical catalog
#                               (total=153), identical series ids and identical
#                               chapter/page counts on every series sampled.
#   toonilyme   -> beehentai    Both read api.toontop.io with the same routes
#                               (/titles/search, /titles/by-slug/...). Identical
#                               catalog (total=8706) and identical ids.
#   mangapanda  -> mangahub     Same mghcdn.com image store and the same slug
#                               space (mangahub ids resolve on mangapanda), but
#                               mangapanda serves a 6-page preview of EVERY
#                               chapter where mangahub serves all 54.
#
# Their code and tests stay in the tree -- the tests are offline and green, and
# they are the ready-made replacement if one of the kept sources dies. Wiring
# one in means removing the source it collides with in the same commit.

def _register_builtin_connectors() -> None:
    """Register all built-in connectors. Fail loudly on any error."""
    builtins: tuple[tuple[str, type[SourceConnector]], ...] = (
        (AkumaConnector.SOURCE_TYPE, AkumaConnector),
        (AsuraScansConnector.SOURCE_TYPE, AsuraScansConnector),
        (CoffeeMangaConnector.SOURCE_TYPE, CoffeeMangaConnector),
        (LocalFilesystemConnector.SOURCE_TYPE, LocalFilesystemConnector),
        (MangaDexConnector.SOURCE_TYPE, MangaDexConnector),
        (MangaKatanaConnector.SOURCE_TYPE, MangaKatanaConnector),
        (MangaBuddyConnector.SOURCE_TYPE, MangaBuddyConnector),
        (MangaPillConnector.SOURCE_TYPE, MangaPillConnector),
        (MangaHubConnector.SOURCE_TYPE, MangaHubConnector),
        (MangaFreakConnector.SOURCE_TYPE, MangaFreakConnector),
        (MangaTownConnector.SOURCE_TYPE, MangaTownConnector),
        (NovelCoolConnector.SOURCE_TYPE, NovelCoolConnector),
        (RawkumaConnector.SOURCE_TYPE, RawkumaConnector),
        (RawInuConnector.SOURCE_TYPE, RawInuConnector),
        (Manhwa18Connector.SOURCE_TYPE, Manhwa18Connector),
        (OmegaScansConnector.SOURCE_TYPE, OmegaScansConnector),
        (FanFoxConnector.SOURCE_TYPE, FanFoxConnector),
        (DemonicScansConnector.SOURCE_TYPE, DemonicScansConnector),
        (ToonilyConnector.SOURCE_TYPE, ToonilyConnector),
        (NHentaiConnector.SOURCE_TYPE, NHentaiConnector),
        (WeebCentralConnector.SOURCE_TYPE, WeebCentralConnector),
        (WebtoonsConnector.SOURCE_TYPE, WebtoonsConnector),
        (TapasConnector.SOURCE_TYPE, TapasConnector),
        (PornComic18Connector.SOURCE_TYPE, PornComic18Connector),
        (ThreeHentaiConnector.SOURCE_TYPE, ThreeHentaiConnector),
        (AsmHentaiConnector.SOURCE_TYPE, AsmHentaiConnector),
        (AuroraScansConnector.SOURCE_TYPE, AuroraScansConnector),
        (BbatoConnector.SOURCE_TYPE, BbatoConnector),
        (BeeHentaiConnector.SOURCE_TYPE, BeeHentaiConnector),
        (ComicLandConnector.SOURCE_TYPE, ComicLandConnector),
        (FlameScansConnector.SOURCE_TYPE, FlameScansConnector),
        (FreeAdultComixConnector.SOURCE_TYPE, FreeAdultComixConnector),
        (BaoZiMHConnector.SOURCE_TYPE, BaoZiMHConnector),
        (CManhuaConnector.SOURCE_TYPE, CManhuaConnector),
        (ComicAsuraConnector.SOURCE_TYPE, ComicAsuraConnector),
        (ComicsValleyConnector.SOURCE_TYPE, ComicsValleyConnector),
        (EHentaiConnector.SOURCE_TYPE, EHentaiConnector),
        (GalaxyMangaConnector.SOURCE_TYPE, GalaxyMangaConnector),
        (Hentai20Connector.SOURCE_TYPE, Hentai20Connector),
        (HentaiFoxConnector.SOURCE_TYPE, HentaiFoxConnector),
        (HentaiEraConnector.SOURCE_TYPE, HentaiEraConnector),
        (HariMangaConnector.SOURCE_TYPE, HariMangaConnector),
        (EightMusesConnector.SOURCE_TYPE, EightMusesConnector),
        (ElfToonConnector.SOURCE_TYPE, ElfToonConnector),
        (DoujinsConnector.SOURCE_TYPE, DoujinsConnector),
        # Novel sources (CONTENT_KIND = "novel"): registered unconditionally,
        # but every registry query surface hides them while MM_NOVELS_ENABLED
        # is off (see _novels_enabled) — production stays a manhwa site.
        (ArchiveOrgConnector.SOURCE_TYPE, ArchiveOrgConnector),
        (FreeWebNovelConnector.SOURCE_TYPE, FreeWebNovelConnector),

        (GutenbergConnector.SOURCE_TYPE, GutenbergConnector),

        (NovelBuddyConnector.SOURCE_TYPE, NovelBuddyConnector),
        (NovelArchiveConnector.SOURCE_TYPE, NovelArchiveConnector),
        (NovelFullConnector.SOURCE_TYPE, NovelFullConnector),
        (RoyalRoadConnector.SOURCE_TYPE, RoyalRoadConnector),
        (StandardEbooksConnector.SOURCE_TYPE, StandardEbooksConnector),
        *((cls.SOURCE_TYPE, cls) for cls in _MADARA_CONNECTOR_CLASSES),
    )
    if "1stkissmanga" not in EXCLUDED_CONNECTORS:
        builtins = (
            *builtins[: builtins.index((EightMusesConnector.SOURCE_TYPE, EightMusesConnector)) + 1],
            (FirstKissMangaConnector.SOURCE_TYPE, FirstKissMangaConnector),
            *builtins[builtins.index((EightMusesConnector.SOURCE_TYPE, EightMusesConnector)) + 1 :],
        )
    failures: list[str] = []
    for source_type, connector_cls in builtins:
        if source_type in EXCLUDED_CONNECTORS:
            continue
        try:
            register_connector(source_type, connector_cls)
        except Exception as exc:
            failures.append(f"{source_type}: {exc}")
    if failures:
        raise ConnectorRegistrationError(
            "Failed to register built-in connectors:\n- " + "\n- ".join(failures)
        )


def validate_registry(*, require_browsable: set[str] | frozenset[str] | None = None) -> None:
    """Ensure required connectors are present and browsable."""
    required = require_browsable or REQUIRED_BROWSABLE_CONNECTORS
    installed = {descriptor.source_type for descriptor in list_installed_connectors()}
    missing = sorted(required - installed)
    if missing:
        raise ConnectorRegistrationError(
            "Missing required browsable connectors: "
            f"{', '.join(missing)}. Installed: {', '.join(sorted(installed)) or 'none'}."
        )

    for source_type in sorted(required):
        descriptor = _descriptor_for(_REGISTRY[source_type])
        if not descriptor.browsable:
            raise ConnectorRegistrationError(
                f"Required connector '{source_type}' is not browsable."
            )


def log_registered_connectors(target_logger: logging.Logger | None = None) -> None:
    """Log every connector in the active registry."""
    active_logger = target_logger or logger
    active_logger.info("Registered connectors:")
    for descriptor in list_installed_connectors():
        flags: list[str] = []
        if descriptor.browsable:
            flags.append("browsable")
        if descriptor.supports_import:
            flags.append("import")
        flag_text = ", ".join(flags) if flags else "none"
        active_logger.info("  - %s (%s) [%s]", descriptor.source_type, descriptor.name, flag_text)
    active_logger.info(
        "Browsable connectors for GET /sources: %s",
        ", ".join(
            descriptor.source_type
            for descriptor in list_installed_connectors(browsable_only=True)
        )
        or "none",
    )


def registry_snapshot() -> dict[str, object]:
    """Return a debug snapshot of the active registry module state."""
    return {
        "registry_id": id(_REGISTRY),
        "connector_types": list_connector_types(),
        "browsable_types": [
            descriptor.source_type
            for descriptor in list_installed_connectors(browsable_only=True)
        ],
        "required_browsable": sorted(REQUIRED_BROWSABLE_CONNECTORS),
    }


def list_connector_types() -> list[str]:
    """Return all registered connector source types (novels only when flagged)."""
    novels_on = _novels_enabled()
    return sorted(
        source_type
        for source_type, connector_cls in _REGISTRY.items()
        if novels_on or not _is_novel_class(connector_cls)
    )


def create_connector(source_type: str, **config: Any) -> SourceConnector:
    """Instantiate a connector by source type."""
    connector_cls = _REGISTRY.get(source_type)
    if connector_cls is not None and _is_novel_class(connector_cls) and not _novels_enabled():
        # Flag off => a novel source type does not exist, full stop. Falling
        # through to the unknown-type error keeps every caller's behaviour
        # (404 source_not_found) identical to a source that was never built.
        connector_cls = None
    if connector_cls is None:
        supported = ", ".join(list_connector_types()) or "none"
        raise ValueError(
            f"Unknown source type '{source_type}'. Supported types: {supported}."
        )
    if source_type == LocalFilesystemConnector.SOURCE_TYPE and "root_path" not in config:
        raise ValueError("local_filesystem connector requires root_path.")
    if source_type in _CONFIGLESS_CONNECTORS:
        cached = _INSTANCE_CACHE.get(source_type)
        if cached is not None:
            return cached
        instance = connector_cls()
        _INSTANCE_CACHE[source_type] = instance
        return instance
    return connector_cls(**config)


def get_connector(source_type: str, **config: Any) -> SourceConnector:
    """Alias for create_connector."""
    return create_connector(source_type, **config)


def _descriptor_for(connector_cls: type[SourceConnector]) -> ConnectorDescriptor:
    return ConnectorDescriptor(
        source_type=connector_cls.SOURCE_TYPE,
        name=getattr(connector_cls, "DISPLAY_NAME", connector_cls.SOURCE_TYPE),
        description=getattr(connector_cls, "DESCRIPTION", ""),
        browsable=getattr(connector_cls, "BROWSABLE", True),
        supports_import=getattr(connector_cls, "SUPPORTS_IMPORT", False),
        mature=getattr(connector_cls, "MATURE", False),
        icon_url=connector_icon_url(connector_cls),
        content_kind=getattr(connector_cls, "CONTENT_KIND", "manga"),
        language=getattr(connector_cls, "LANGUAGE", None),
    )


def list_installed_connectors(
    *, browsable_only: bool = False, include_mature: bool = True
) -> list[ConnectorDescriptor]:
    """Return metadata for installed connectors.

    ``include_mature=False`` drops adult (18+) sources -- callers that
    respect the user's ``mature_content_enabled`` preference pass the
    setting through here. The default keeps this a neutral listing so the
    maturity *policy* lives with the browse service, not the registry."""
    novels_on = _novels_enabled()
    descriptors: list[ConnectorDescriptor] = []
    for connector_cls in _REGISTRY.values():
        if not novels_on and _is_novel_class(connector_cls):
            # MM_NOVELS_ENABLED off: novel sources are not merely hidden,
            # they are absent from every listing surface (spec §2).
            continue
        descriptor = _descriptor_for(connector_cls)
        if browsable_only and not descriptor.browsable:
            continue
        if not include_mature and descriptor.mature:
            continue
        descriptors.append(descriptor)
    return sorted(descriptors, key=lambda item: item.name.casefold())


_register_builtin_connectors()
validate_registry()
