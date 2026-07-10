"""Registry for pluggable source connectors."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from connectors.asurascans.connector import AsuraScansConnector
from connectors.base import SourceConnector
from connectors.local_filesystem.connector import LocalFilesystemConnector
from connectors.mangadex.connector import MangaDexConnector
from connectors.mangakatana.connector import MangaKatanaConnector
from connectors.demonicscans.connector import DemonicScansConnector
from connectors.toonily.connector import ToonilyConnector

logger = logging.getLogger(__name__)

REQUIRED_BROWSABLE_CONNECTORS = frozenset({"asurascans", "mangadex"})

_CONFIGLESS_CONNECTORS = {
    AsuraScansConnector.SOURCE_TYPE,
    MangaDexConnector.SOURCE_TYPE,
    MangaKatanaConnector.SOURCE_TYPE,
    DemonicScansConnector.SOURCE_TYPE,
    ToonilyConnector.SOURCE_TYPE,
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


def _register_builtin_connectors() -> None:
    """Register all built-in connectors. Fail loudly on any error."""
    builtins: tuple[tuple[str, type[SourceConnector]], ...] = (
        (AsuraScansConnector.SOURCE_TYPE, AsuraScansConnector),
        (LocalFilesystemConnector.SOURCE_TYPE, LocalFilesystemConnector),
        (MangaDexConnector.SOURCE_TYPE, MangaDexConnector),
        (MangaKatanaConnector.SOURCE_TYPE, MangaKatanaConnector),
        (DemonicScansConnector.SOURCE_TYPE, DemonicScansConnector),
        (ToonilyConnector.SOURCE_TYPE, ToonilyConnector),
    )
    failures: list[str] = []
    for source_type, connector_cls in builtins:
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
    """Return all registered connector source types."""
    return sorted(_REGISTRY)


def create_connector(source_type: str, **config: Any) -> SourceConnector:
    """Instantiate a connector by source type."""
    connector_cls = _REGISTRY.get(source_type)
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
    )


def list_installed_connectors(
    *, browsable_only: bool = False, include_mature: bool = True
) -> list[ConnectorDescriptor]:
    """Return metadata for installed connectors.

    ``include_mature=False`` drops adult (18+) sources -- callers that
    respect the user's ``mature_content_enabled`` preference pass the
    setting through here. The default keeps this a neutral listing so the
    maturity *policy* lives with the browse service, not the registry."""
    descriptors: list[ConnectorDescriptor] = []
    for connector_cls in _REGISTRY.values():
        descriptor = _descriptor_for(connector_cls)
        if browsable_only and not descriptor.browsable:
            continue
        if not include_mature and descriptor.mature:
            continue
        descriptors.append(descriptor)
    return sorted(descriptors, key=lambda item: item.name.casefold())


_register_builtin_connectors()
validate_registry()
