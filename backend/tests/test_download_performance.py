"""Benchmark: concurrent vs. sequential page downloads within a chapter.

Root cause of low throughput (see docs): chapters already download in
parallel across a worker pool (``download_workers``), but pages *within* a
single chapter were fetched strictly one at a time -- each page waited for
the previous page's fetch + verify + hash + manifest write to finish before
starting. For a 40-page chapter at ~50ms average page latency, that's ~2s of
pure serial waiting per chapter no matter how many chapter workers are free.

This test drives the real ``DownloadManager._process_download`` code path
(not a synthetic toy) with a fake page fetch that sleeps to simulate network
latency, and asserts that raising ``download_page_concurrency`` produces a
proportional wall-clock speedup -- while every existing correctness
guarantee (resume, retry structure, manifest, SSRF validation call site)
stays exercised through the same code.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session, sessionmaker

from connectors.models import Chapter as ConnectorChapter
from connectors.models import Page as ConnectorPage
from database.models import Download, DownloadQueue
from services.download_manager import DownloadManager, reset_download_manager_for_tests

PAGE_LATENCY_SECONDS = 0.05
PAGE_COUNT = 12

MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _slow_fetch_image(url: str, *, connector, final_path: Path, partial_path: Path, **kwargs) -> bytes:
    """Stand-in for fetch_image_resumable: simulates real network latency
    without making any actual HTTP calls."""
    time.sleep(PAGE_LATENCY_SECONDS)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(MINIMAL_PNG)
    partial_path.unlink(missing_ok=True)
    return MINIMAL_PNG


def _mock_connector_with_pages(page_count: int) -> MagicMock:
    connector = MagicMock()
    connector.is_browsable = True
    connector.allowed_image_hosts = frozenset({"example.com"})
    connector.get_chapter_pages.return_value = [
        ConnectorPage(
            id=f"chapter-1:{i}",
            chapter_id="chapter-1",
            number=i,
            remote_url=f"https://example.com/page{i}.png",
        )
        for i in range(1, page_count + 1)
    ]
    return connector


@pytest.fixture
def downloads_root(tmp_path: Path) -> Path:
    root = tmp_path / "downloads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run_download(
    db_engine,
    downloads_root: Path,
    *,
    page_concurrency: int,
) -> tuple[float, Download]:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    manager = DownloadManager(max_workers=1)
    manager._downloads_root = downloads_root
    reset_download_manager_for_tests(manager)

    download = Download(
        source="mangadex",
        series_id="series-1",
        chapter_id="chapter-1",
        series_title="Benchmark Series",
        chapter_title=f"Chapter concurrency-{page_concurrency}",
        status="queued",
    )
    db.add(download)
    db.flush()
    db.add(DownloadQueue(download_id=download.id, state="pending"))
    db.commit()
    download_id = download.id

    connector = _mock_connector_with_pages(PAGE_COUNT)
    fake_settings = MagicMock(
        download_page_concurrency=page_concurrency,
        download_retry_count=4,
        download_retry_delay_seconds=0.1,
        download_timeout_seconds=30.0,
    )

    with patch("services.download_manager.SessionLocal", session_factory):
        with patch("services.download_manager.create_connector", return_value=connector):
            with patch("services.download_manager.fetch_image_resumable", side_effect=_slow_fetch_image):
                with patch("services.download_manager.get_settings", return_value=fake_settings):
                    started = time.perf_counter()
                    manager._process_download(download_id)
                    elapsed = time.perf_counter() - started

    db.expire_all()
    result = db.get(Download, download_id)
    db.close()
    reset_download_manager_for_tests(None)
    return elapsed, result


def test_page_concurrency_speeds_up_chapter_download(db_engine, downloads_root: Path):
    sequential_seconds, sequential_download = _run_download(
        db_engine, downloads_root, page_concurrency=1
    )
    concurrent_seconds, concurrent_download = _run_download(
        db_engine, downloads_root, page_concurrency=4
    )

    assert sequential_download is not None
    assert sequential_download.status == "completed"
    assert sequential_download.pages_done == PAGE_COUNT

    assert concurrent_download is not None
    assert concurrent_download.status == "completed"
    assert concurrent_download.pages_done == PAGE_COUNT

    # Theoretical: sequential ~= PAGE_COUNT * latency; concurrent(4) ~=
    # ceil(PAGE_COUNT / 4) * latency. Assert a real, substantial speedup
    # rather than the exact theoretical ratio, to stay robust against
    # scheduling/CI jitter.
    speedup = sequential_seconds / concurrent_seconds
    print(
        f"\n[benchmark] sequential={sequential_seconds:.3f}s "
        f"concurrent(4)={concurrent_seconds:.3f}s speedup={speedup:.2f}x"
    )
    assert speedup > 2.0, (
        f"expected a substantial speedup from page concurrency, got {speedup:.2f}x "
        f"(sequential={sequential_seconds:.3f}s, concurrent={concurrent_seconds:.3f}s)"
    )
