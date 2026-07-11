"""Application configuration.

Single source of truth for runtime settings. Reads the shared
`config/settings.json` at the repo root and layers environment overrides on top.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

# backend/core/config.py -> parents[2] == repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
# Where user preferences (download/mature settings) are persisted. Overridable
# via MM_SETTINGS_PATH so the container can write to its /data volume: the
# packaged app lives at /app, where the repo-relative default resolves outside
# the writable tree (parents[2] == "/").
SETTINGS_PATH = (
    Path(os.environ["MM_SETTINGS_PATH"])
    if os.getenv("MM_SETTINGS_PATH")
    else REPO_ROOT / "config" / "settings.json"
)

APP_VERSION = "0.1.0"


class Settings(BaseModel):
    """Typed view over config/settings.json plus a few runtime-only fields."""

    # Tolerate unknown keys so settings.json can grow without breaking startup.
    model_config = {"extra": "allow"}

    project_name: str = "ManhwaManiacs"
    default_project: str = "ManhwaManiacs"

    # Adult/18+ content gate. Hidden by default; the user must explicitly
    # opt in (with an age confirmation on the client) before mature sources,
    # search results, and recommendations are shown. Persisted in
    # config/settings.json like the other user-facing preferences.
    mature_content_enabled: bool = False

    # Runtime-only (not persisted in settings.json).
    version: str = APP_VERSION
    db_path: str = str(REPO_ROOT / "backend" / "manhwamaniacs.db")
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    downloads_path: str = str(REPO_ROOT / "library" / "downloads")
    # How many chapters may download at once, across all series. User-
    # configurable from Settings -> Downloads; defaults to fully sequential.
    download_concurrent_chapters: int = 1
    # Concurrent page fetches *within* a single chapter. Page images have no
    # server-side rate limit of their own (unlike connector metadata calls),
    # so this is the only throttle on how many page requests hit a source at
    # once. Independent of download_concurrent_chapters -- this is a page
    # limit, not a chapter limit.
    download_page_concurrency: int = 4
    download_retry_count: int = 4
    download_retry_delay_seconds: float = 0.75
    download_timeout_seconds: float = 30.0

    # OCR pipeline settings
    ocr_engine: str = "tesseract"
    ocr_workers: int = 2
    ocr_language: str = "eng"
    ocr_max_retries: int = 3
    ocr_max_page_retries: int = 2
    ocr_retry_backoff_base: float = 1.0
    ocr_auto_queue: bool = False
    ocr_max_image_pixels: int = 50_000_000
    ocr_queue_depth_limit: int = 1000
    ocr_enable_preprocessing: bool = True

    # Automatic update system
    update_workers: int = 1
    update_check_interval_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    """Load settings once and cache them for the process lifetime."""
    data: dict = {}
    if SETTINGS_PATH.exists():
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))

    extra_origins = os.getenv("CORS_ORIGINS")
    if extra_origins:
        data["cors_origins"] = [o.strip() for o in extra_origins.split(",") if o.strip()]

    # Deployment overrides: point the database and downloads at the mounted
    # data volume (see docker-compose.yml) without editing settings.json.
    db_path_override = os.getenv("MM_DB_PATH")
    if db_path_override:
        data["db_path"] = db_path_override
    downloads_override = os.getenv("MM_DOWNLOADS_PATH")
    if downloads_override:
        data["downloads_path"] = downloads_override

    return Settings(**data)


def update_persisted_settings(**changes: object) -> Settings:
    """Merge ``changes`` into config/settings.json and refresh the cached
    Settings instance immediately, so callers see the new values on their
    very next ``get_settings()`` call -- no process restart required."""
    data: dict = {}
    if SETTINGS_PATH.exists():
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    data.update(changes)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    get_settings.cache_clear()
    return get_settings()
