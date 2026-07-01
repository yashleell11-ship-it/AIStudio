from __future__ import annotations

from services.download_manager import DownloadManager
from services.ocr_pipeline import OcrPipelineManager


def test_download_manager_clears_stop_event_on_restart():
  manager = DownloadManager(max_workers=1)
  manager.start()
  manager.stop()
  assert manager._stop_event.is_set()

  manager.start()
  try:
    assert not manager._stop_event.is_set()
    assert manager._started
  finally:
    manager.stop()


def test_ocr_manager_clears_stop_event_on_restart():
  manager = OcrPipelineManager(max_workers=1)
  manager.start()
  manager.stop()
  assert manager._stop_event.is_set()

  manager.start()
  try:
    assert not manager._stop_event.is_set()
    assert manager._started
  finally:
    manager.stop()
