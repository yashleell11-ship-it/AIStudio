"""Tests for hardened download support utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.download_support import (
    PRIORITY_BACKGROUND,
    PRIORITY_CURRENT_CHAPTER,
    PRIORITY_CURRENT_SERIES,
    ChapterManifest,
    PageManifestEntry,
    ensure_disk_space,
    infer_queue_priority,
    verify_image_bytes,
    verify_image_file,
)


MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_verify_image_bytes_accepts_png():
    assert verify_image_bytes(MINIMAL_PNG) is True
    assert verify_image_bytes(b"") is False
    assert verify_image_bytes(b"not-an-image") is False


def test_verify_image_file(tmp_path: Path):
    valid = tmp_path / "001.png"
    valid.write_bytes(MINIMAL_PNG)
    assert verify_image_file(valid) is True

    empty = tmp_path / "002.png"
    empty.write_bytes(b"")
    assert verify_image_file(empty) is False


def test_infer_queue_priority():
    assert infer_queue_priority(chapter_count=1, series_queue=False) == PRIORITY_CURRENT_CHAPTER
    assert infer_queue_priority(chapter_count=3, series_queue=False) == PRIORITY_CURRENT_SERIES
    assert infer_queue_priority(chapter_count=3, series_queue=True) == PRIORITY_BACKGROUND
    assert infer_queue_priority(chapter_count=1, series_queue=False, explicit=50) == 50


def test_chapter_manifest_roundtrip(tmp_path: Path):
    manifest = ChapterManifest(
        download_id=7,
        chapter_id="chapter-1",
        pages=[
            PageManifestEntry(
                index=1,
                filename="001.png",
                remote_url="https://example.com/1.png",
                sha256="abc",
                size=123,
            )
        ],
    )
    manifest.save(tmp_path)
    loaded = ChapterManifest().load(tmp_path)
    assert loaded is not None
    assert loaded.download_id == 7
    assert loaded.completed_count() == 1


def test_disk_space_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "services.download_support.disk_stats",
        lambda _path: (10_000_000_000, 9_000_000_000, 600 * 1024 * 1024),
    )
    warnings = ensure_disk_space(
        tmp_path,
        required_bytes=1_000_000,
        min_free_bytes=100 * 1024 * 1024,
        warn_free_bytes=1024 * 1024 * 1024,
    )
    assert warnings
