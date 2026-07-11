"""Per-site configuration for Madara-theme WordPress manga sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class MadaraSiteConfig:
    """One Madara-theme site registered as a browsable connector."""

    source_id: str
    display_name: str
    base_url: str
    # URL path segment for series/chapters: ``manga`` (CoffeeManga-style) or
    # ``serie`` (Toonily-style).
    url_segment: str = "manga"
    mature: bool = False
    use_cf: bool = True
    description: str = ""
    page_size: int = 20
    extra_image_hosts: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        segment = self.url_segment.strip().strip("/")
        if not segment or "/" in segment:
            raise ValueError(f"url_segment must be a single path segment, got {self.url_segment!r}")
        object.__setattr__(self, "url_segment", segment)

    @property
    def site_host(self) -> str:
        host = urlparse(self.base_url).hostname
        if not host:
            raise ValueError(f"Invalid base_url: {self.base_url!r}")
        return host.lower()

    @property
    def image_hosts(self) -> frozenset[str]:
        hosts = {self.site_host, *self.extra_image_hosts}
        return frozenset(hosts)
