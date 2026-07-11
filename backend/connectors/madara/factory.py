"""Build Madara connector classes from site configs."""

from __future__ import annotations

from typing import TypeVar

from connectors.base import SourceConnector
from connectors.madara.config import MadaraSiteConfig
from connectors.madara.connector import MadaraConnector

_T = TypeVar("_T", bound=type[SourceConnector])

_CLASS_CACHE: dict[str, type[SourceConnector]] = {}


def build_madara_connector_class(config: MadaraSiteConfig) -> type[SourceConnector]:
    """Return a unique connector class for ``config`` (cached by source_id)."""
    cached = _CLASS_CACHE.get(config.source_id)
    if cached is not None:
        return cached

    description = config.description or (
        f"Browse and read from {config.display_name}. "
        "Images are proxied through ManhwaManiacs."
    )
    class_name = "".join(part.title() for part in config.source_id.split("_"))
    if not class_name.endswith("Connector"):
        class_name = f"{class_name}Connector"

    connector_cls = type(
        class_name,
        (MadaraConnector,),
        {
            "CONFIG": config,
            "SOURCE_TYPE": config.source_id,
            "DISPLAY_NAME": config.display_name,
            "DESCRIPTION": description,
            "MATURE": config.mature,
            "__module__": __name__,
        },
    )
    _CLASS_CACHE[config.source_id] = connector_cls
    return connector_cls


def madara_connector_classes(
    configs: tuple[MadaraSiteConfig, ...] | list[MadaraSiteConfig],
) -> list[type[SourceConnector]]:
    """Build connector classes for every config (deduped by source_id)."""
    seen: set[str] = set()
    classes: list[type[SourceConnector]] = []
    for config in configs:
        if config.source_id in seen:
            continue
        seen.add(config.source_id)
        classes.append(build_madara_connector_class(config))
    return classes
