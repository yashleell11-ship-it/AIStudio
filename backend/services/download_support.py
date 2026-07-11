"""Download reliability helpers: verification, disk, retry, manifest, metrics."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from connectors.base import SourceConnector
from core.errors import AppError
from services.outbound_security import validate_outbound_url

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = ".manhwamaniacs-download.json"
PARTIAL_SUFFIX = ".partial"

PRIORITY_CURRENT_CHAPTER = 0
PRIORITY_CURRENT_SERIES = 10
PRIORITY_BACKGROUND = 100

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
DEFAULT_FETCH_RETRIES = 4
DEFAULT_BACKOFF_BASE = 0.75


class DiskSpaceError(RuntimeError):
    """Raised when the downloads volume is too low on free space."""


class PermanentDownloadError(RuntimeError):
    """Non-retryable download failure."""


class TransientDownloadError(RuntimeError):
    """Retryable download failure."""


def infer_queue_priority(*, chapter_count: int, series_queue: bool, explicit: int | None = None) -> int:
    if explicit is not None:
        return explicit
    if series_queue:
        return PRIORITY_BACKGROUND
    if chapter_count == 1:
        return PRIORITY_CURRENT_CHAPTER
    return PRIORITY_CURRENT_SERIES


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_image_bytes(content: bytes) -> bool:
    if len(content) < 12:
        return False
    if content.startswith(b"\xff\xd8\xff"):
        return True
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return True
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return True
    if content.startswith(b"BM"):
        return True
    return False


def verify_image_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.stat().st_size <= 0:
        return False
    try:
        header = path.read_bytes()[:16]
    except OSError:
        return False
    return verify_image_bytes(header)


def disk_stats(path: Path) -> tuple[int, int, int]:
    usage = shutil.disk_usage(path)
    return usage.total, usage.used, usage.free


def ensure_disk_space(
    path: Path,
    *,
    required_bytes: int,
    min_free_bytes: int,
    warn_free_bytes: int,
) -> list[str]:
    warnings: list[str] = []
    _total, _used, free = disk_stats(path)
    if free < min_free_bytes:
        raise DiskSpaceError(
            f"Insufficient disk space: {free} bytes free, need at least {min_free_bytes}."
        )
    if free < warn_free_bytes:
        warnings.append(
            f"Low disk space warning: {free // (1024 * 1024)} MB free."
        )
    if required_bytes > 0 and free < required_bytes + min_free_bytes:
        warnings.append(
            f"Estimated download may require {required_bytes // (1024 * 1024)} MB."
        )
    return warnings


def is_transient_http_status(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUS


def is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, TransientDownloadError):
        return True
    if isinstance(exc, PermanentDownloadError):
        return False
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.ConnectError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return is_transient_http_status(exc.response.status_code)
    if isinstance(exc, httpx.HTTPError):
        return True
    return False


def estimate_chapter_bytes(page_count: int, *, bytes_per_page: int = 512_000) -> int:
    return max(page_count, 1) * bytes_per_page


@dataclass(slots=True)
class PageManifestEntry:
    index: int
    filename: str
    remote_url: str
    sha256: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "filename": self.filename,
            "remote_url": self.remote_url,
            "sha256": self.sha256,
            "size": self.size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageManifestEntry:
        return cls(
            index=int(data["index"]),
            filename=str(data["filename"]),
            remote_url=str(data["remote_url"]),
            sha256=str(data["sha256"]),
            size=int(data["size"]),
        )


@dataclass(slots=True)
class ChapterManifest:
    version: int = 1
    download_id: int | None = None
    chapter_id: str = ""
    pages: list[PageManifestEntry] = field(default_factory=list)

    def path_for(self, chapter_dir: Path) -> Path:
        return chapter_dir / MANIFEST_FILENAME

    def load(self, chapter_dir: Path) -> ChapterManifest | None:
        manifest_path = self.path_for(chapter_dir)
        if not manifest_path.is_file():
            return None
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        pages = [
            PageManifestEntry.from_dict(item)
            for item in payload.get("pages", [])
            if isinstance(item, dict)
        ]
        return ChapterManifest(
            version=int(payload.get("version", 1)),
            download_id=payload.get("download_id"),
            chapter_id=str(payload.get("chapter_id", "")),
            pages=pages,
        )

    def save(self, chapter_dir: Path) -> None:
        manifest_path = self.path_for(chapter_dir)
        payload = {
            "version": self.version,
            "download_id": self.download_id,
            "chapter_id": self.chapter_id,
            "pages": [page.to_dict() for page in self.pages],
        }
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def entry_for_index(self, index: int) -> PageManifestEntry | None:
        for page in self.pages:
            if page.index == index:
                return page
        return None

    def completed_count(self) -> int:
        return len(self.pages)


def fetch_image_resumable(
    url: str,
    *,
    connector: SourceConnector,
    final_path: Path,
    partial_path: Path,
    max_retries: int = DEFAULT_FETCH_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    timeout: float = 30.0,
) -> bytes:
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            return _fetch_image_attempt(
                url,
                connector=connector,
                final_path=final_path,
                partial_path=partial_path,
                timeout=timeout,
            )
        except PermanentDownloadError as exc:
            raise RuntimeError(str(exc)) from exc
        except (TransientDownloadError, httpx.HTTPError, OSError) as exc:
            last_error = exc
            if not is_transient_error(exc) or attempt + 1 >= max_retries:
                break
            sleep_for = backoff_base * (2**attempt)
            time.sleep(sleep_for)

    message = str(last_error) if last_error else "Unknown image fetch error"
    raise RuntimeError(message) from last_error


def _fetch_image_attempt(
    url: str,
    *,
    connector: SourceConnector,
    final_path: Path,
    partial_path: Path,
    timeout: float,
) -> bytes:
    try:
        validate_outbound_url(url, connector)
    except AppError as exc:
        raise PermanentDownloadError(str(exc)) from exc

    existing = partial_path.stat().st_size if partial_path.is_file() else 0
    headers: dict[str, str] = dict(connector.image_fetch_headers())
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"

    try:
        with httpx.stream(
            "GET",
            url,
            timeout=timeout,
            follow_redirects=False,
            headers=headers,
        ) as response:
            if response.is_redirect:
                raise PermanentDownloadError(
                    "Remote host returned a redirect, which is not permitted."
                )
            if response.status_code == 416 and existing > 0:
                partial_path.unlink(missing_ok=True)
                existing = 0
                with httpx.stream(
                    "GET",
                    url,
                    timeout=timeout,
                    follow_redirects=False,
                    headers=dict(connector.image_fetch_headers()),
                ) as retry_response:
                    if retry_response.is_redirect:
                        raise PermanentDownloadError(
                            "Remote host returned a redirect, which is not permitted."
                        )
                    return _write_stream(retry_response, final_path, partial_path, existing=0)

            if response.status_code in RETRYABLE_STATUS:
                raise TransientDownloadError(f"Retryable HTTP {response.status_code}")
            if response.status_code >= 400:
                if is_transient_http_status(response.status_code):
                    raise TransientDownloadError(f"HTTP {response.status_code}")
                raise PermanentDownloadError(f"HTTP {response.status_code}")

            if response.status_code == 206:
                return _write_stream(response, final_path, partial_path, existing=existing)

            if existing > 0:
                partial_path.unlink(missing_ok=True)
            return _write_stream(response, final_path, partial_path, existing=0)
    except httpx.TimeoutException as exc:
        raise TransientDownloadError("Request timed out.") from exc
    except httpx.ConnectError as exc:
        raise TransientDownloadError("Connection failed.") from exc


def _write_stream(
    response: httpx.Response,
    final_path: Path,
    partial_path: Path,
    *,
    existing: int,
) -> bytes:
    mode = "ab" if existing > 0 else "wb"
    partial_path.parent.mkdir(parents=True, exist_ok=True)
    with partial_path.open(mode) as handle:
        for chunk in response.iter_bytes():
            if chunk:
                handle.write(chunk)

    content = partial_path.read_bytes()
    if not content or not verify_image_bytes(content):
        partial_path.unlink(missing_ok=True)
        raise TransientDownloadError("Downloaded image failed verification.")

    final_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path.replace(final_path)
    return content


@dataclass(slots=True)
class ProfileSample:
    fetch_ms: float = 0.0
    verify_ms: float = 0.0
    import_ms: float = 0.0
    total_ms: float = 0.0


class DownloadProfiler:
    def __init__(self) -> None:
        self._last: ProfileSample | None = None
        self._totals = {"fetch_ms": 0.0, "verify_ms": 0.0, "import_ms": 0.0, "total_ms": 0.0}
        self._count = 0

    def record(self, sample: ProfileSample) -> None:
        self._last = sample
        self._count += 1
        self._totals["fetch_ms"] += sample.fetch_ms
        self._totals["verify_ms"] += sample.verify_ms
        self._totals["import_ms"] += sample.import_ms
        self._totals["total_ms"] += sample.total_ms

    def snapshot(self) -> dict[str, Any]:
        if self._count == 0:
            return {"samples": 0, "last": None, "averages_ms": None}
        averages = {
            key: round(self._totals[key] / self._count, 2)
            for key in self._totals
        }
        last = None
        if self._last is not None:
            last = {
                "fetch_ms": round(self._last.fetch_ms, 2),
                "verify_ms": round(self._last.verify_ms, 2),
                "import_ms": round(self._last.import_ms, 2),
                "total_ms": round(self._last.total_ms, 2),
            }
        return {"samples": self._count, "last": last, "averages_ms": averages}


@dataclass(slots=True)
class DownloadMetrics:
    total: int
    completed: int
    failed: int
    remaining: int
    active: int
    storage_used_bytes: int
    storage_free_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "remaining": self.remaining,
            "active": self.active,
            "storage_used_bytes": self.storage_used_bytes,
            "storage_free_bytes": self.storage_free_bytes,
        }


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file() and item.name != MANIFEST_FILENAME and not item.name.endswith(PARTIAL_SUFFIX):
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total
