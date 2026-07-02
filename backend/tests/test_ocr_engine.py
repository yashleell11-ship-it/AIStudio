"""Tests for OCR engine implementations.

Both Tesseract and EasyOCR are fully mocked so these tests do not require the
heavy runtime dependencies or the Tesseract binary.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from services.ocr_engine import (
    EasyOcrEngine,
    OcrEngineNotAvailable,
    OcrRecognitionError,
    OcrResult,
    TesseractEngine,
    _clear_easyocr_cache,
    _preprocess_image,
    get_easyocr_cache_stats,
    get_ocr_engine,
)


class TestPreprocessImage:
    def test_resize_large_image(self) -> None:
        img = Image.new("RGB", (4000, 3000), color="white")
        processed = _preprocess_image(img, max_size=2000)
        assert max(processed.size) <= 2000
        assert processed.mode == "L"

    def test_no_resize_small_image(self) -> None:
        img = Image.new("RGB", (100, 100), color="white")
        processed = _preprocess_image(img, max_size=2000)
        assert processed.size == (100, 100)

    def test_grayscale_conversion(self) -> None:
        img = Image.new("RGBA", (100, 100), color="red")
        processed = _preprocess_image(img)
        assert processed.mode == "L"


class TestTesseractEngine:
    def test_recognize(self) -> None:
        """TesseractEngine parses pytesseract output into an OcrResult."""
        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_data.return_value = {
            "text": ["", "Hello", "", "World"],
            "conf": [-1, 95, -1, 88],
            "left": [0, 10, 0, 20],
            "top": [0, 10, 0, 20],
            "width": [0, 50, 0, 50],
            "height": [0, 20, 0, 20],
        }
        mock_pytesseract.get_tesseract_version.return_value = "5.0.0"

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            engine = TesseractEngine(language="eng")
            img = Image.new("RGB", (100, 100))
            result = engine.recognize(img, preprocess=False)

        assert result.text == "Hello World"
        assert result.confidence == pytest.approx(91.5 / 100.0)
        assert len(result.boxes) == 2
        assert result.boxes[0]["conf"] == 95
        assert result.elapsed_ms >= 0

    def test_missing_dependency(self) -> None:
        """Engine raises OcrEngineNotAvailable when pytesseract is absent."""
        with patch.dict(sys.modules, {"pytesseract": None}):
            with pytest.raises(OcrEngineNotAvailable, match="pytesseract is not installed"):
                TesseractEngine()

    def test_recognition_error(self) -> None:
        """Engine raises OcrRecognitionError on processing failure."""
        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_data.side_effect = RuntimeError("tesseract crash")
        mock_pytesseract.get_tesseract_version.return_value = "5.0.0"

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            engine = TesseractEngine()
            with pytest.raises(OcrRecognitionError, match="Tesseract recognition failed"):
                engine.recognize(Image.new("RGB", (100, 100)), preprocess=False)


class TestEasyOcrEngine:
    def test_recognize(self) -> None:
        """EasyOcrEngine parses easyocr output into an OcrResult."""
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = [
            ([[0, 0], [10, 0], [10, 10], [0, 10]], "Hello", 0.95),
            ([[20, 20], [30, 20], [30, 30], [20, 30]], "World", 0.88),
        ]
        mock_easyocr = MagicMock()
        mock_easyocr.Reader.return_value = mock_reader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            engine = EasyOcrEngine(languages=["en"])
            img = Image.new("RGB", (100, 100))
            result = engine.recognize(img, preprocess=False)

        assert result.text == "Hello World"
        assert result.confidence == pytest.approx((0.95 + 0.88) / 2)
        assert len(result.boxes) == 2
        assert result.elapsed_ms >= 0
        # In the numpy-present path, EasyOCR should receive an array-like object.
        assert mock_reader.readtext.call_args.args

    def test_missing_dependency(self) -> None:
        """Engine raises OcrEngineNotAvailable when easyocr is absent."""
        with patch.dict(sys.modules, {"easyocr": None}):
            engine = EasyOcrEngine(languages=["en"])
            with pytest.raises(OcrEngineNotAvailable, match="easyocr is not installed"):
                engine._ensure_reader()

    def test_recognize_without_numpy_uses_temp_file_and_cleans_up(self, tmp_path) -> None:
        """Regression: without numpy, EasyOCR should use a temp PNG path and remove it."""
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = [
            ([[0, 0], [10, 0], [10, 10], [0, 10]], "Hello", 0.95),
        ]
        mock_easyocr = MagicMock()
        mock_easyocr.Reader.return_value = mock_reader

        import tempfile

        created_paths: list[str] = []
        original_named_tempfile = tempfile.NamedTemporaryFile

        def fake_named_tempfile(*args, **kwargs):
            kwargs["dir"] = tmp_path
            handle = original_named_tempfile(*args, **kwargs)
            created_paths.append(handle.name)
            return handle

        with patch.dict(sys.modules, {"easyocr": mock_easyocr, "numpy": None}):
            with patch("tempfile.NamedTemporaryFile", side_effect=fake_named_tempfile):
                engine = EasyOcrEngine(languages=["en"])
                img = Image.new("RGB", (32, 32))
                result = engine.recognize(img, preprocess=False)

        assert result.text == "Hello"
        assert created_paths, "expected a temp file to be created"
        # EasyOCR must receive a file path in this mode.
        assert isinstance(mock_reader.readtext.call_args.args[0], str)
        assert mock_reader.readtext.call_args.args[0] == created_paths[-1]
        # Temp file must be deleted.
        assert not tmp_path.joinpath(Path(created_paths[-1]).name).exists()


class TestEasyOcrReaderCaching:
    """Regression tests: EasyOCR Reader must not be recreated for every chapter.

    Root cause: EasyOCR eagerly loads PyTorch models.  Before the cache fix,
    every ``OcrPipelineManager._process_job()`` called ``get_ocr_engine()``,
    which created a new ``EasyOcrEngine`` instance with ``_reader = None``.
    Each instance then called ``easyocr.Reader(...)``, reloading the model.

    Fix: thread-local cache so all ``EasyOcrEngine`` instances on the same
    worker thread share the same ``Reader``.
    """

    def test_reader_cached_across_instances_same_thread(self) -> None:
        """Multiple EasyOcrEngine instances on the same thread reuse the Reader."""
        mock_reader = MagicMock()
        mock_easyocr = MagicMock()
        mock_easyocr.Reader.return_value = mock_reader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            engine1 = EasyOcrEngine(languages=["en"])
            engine1._ensure_reader()

            engine2 = EasyOcrEngine(languages=["en"])
            engine2._ensure_reader()

            engine3 = EasyOcrEngine(languages=["en"])
            engine3._ensure_reader()

        # Reader should only be created once despite 3 engine instances
        mock_easyocr.Reader.assert_called_once()
        assert get_easyocr_cache_stats()["cached_count"] == 1

    def test_reader_created_once_per_thread(self) -> None:
        """Each thread gets its own Reader; no cross-thread sharing."""
        import threading

        mock_reader = MagicMock()
        mock_easyocr = MagicMock()
        mock_easyocr.Reader.return_value = mock_reader

        call_count = 0
        original_reader = mock_easyocr.Reader

        def counting_reader(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_reader(*args, **kwargs)

        mock_easyocr.Reader = counting_reader

        def worker():
            with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
                engine = EasyOcrEngine(languages=["en"])
                engine._ensure_reader()

        threads = [
            threading.Thread(target=worker, name=f"worker-{i}")
            for i in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # One Reader per thread = 3 total creations
        assert call_count == 3

    def test_reader_cached_per_language_combo(self) -> None:
        """Different language combos get separate cached readers."""
        mock_reader = MagicMock()
        mock_easyocr = MagicMock()
        mock_easyocr.Reader.return_value = mock_reader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            engine_en = EasyOcrEngine(languages=["en"])
            engine_en._ensure_reader()

            engine_ja = EasyOcrEngine(languages=["ja"])
            engine_ja._ensure_reader()

            engine_en2 = EasyOcrEngine(languages=["en"])
            engine_en2._ensure_reader()

        # Reader called twice: once for "en", once for "ja"
        assert mock_easyocr.Reader.call_count == 2
        cache_stats = get_easyocr_cache_stats()
        assert cache_stats["cached_count"] == 2

    def test_clear_cache_removes_readers(self) -> None:
        """_clear_easyocr_cache() removes all cached readers."""
        mock_reader = MagicMock()
        mock_easyocr = MagicMock()
        mock_easyocr.Reader.return_value = mock_reader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            engine = EasyOcrEngine(languages=["en"])
            engine._ensure_reader()
            assert get_easyocr_cache_stats()["cached_count"] == 1

            _clear_easyocr_cache()
            assert get_easyocr_cache_stats()["cached_count"] == 0


class TestTesseractBehaviorUnchanged:
    """Tesseract does not use the EasyOCR cache and remains per-instance."""

    def test_tesseract_instances_are_independent(self) -> None:
        """Each TesseractEngine instance creates its own pytesseract reference."""
        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_data.return_value = {
            "text": [""], "conf": [-1], "left": [0], "top": [0],
            "width": [0], "height": [0],
        }
        mock_pytesseract.get_tesseract_version.return_value = "5.0.0"

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            engine1 = TesseractEngine(language="eng")
            engine2 = TesseractEngine(language="eng")

            engine1.recognize(Image.new("RGB", (10, 10)), preprocess=False)
            engine2.recognize(Image.new("RGB", (10, 10)), preprocess=False)

        # Tesseract uses the module-level pytesseract, not a cached reader.
        # image_to_data is called twice (once per engine, but same module).
        assert mock_pytesseract.image_to_data.call_count == 2


class TestEasyOcrCacheBenchmark:
    """Benchmark proving the cache eliminates redundant Reader creation."""

    def test_chapter_simulation_reader_count(self) -> None:
        """Simulate 10 chapters on 2 worker threads: 2 readers, not 10."""
        import threading

        mock_reader = MagicMock()
        mock_easyocr = MagicMock()
        mock_easyocr.Reader.return_value = mock_reader

        call_count = 0
        original = mock_easyocr.Reader

        def counting(*a, **k):
            nonlocal call_count
            call_count += 1
            return original(*a, **k)

        mock_easyocr.Reader = counting

        # Simulate 2 worker threads processing 5 chapters each
        chapters_per_thread = 5
        thread_count = 2

        def worker():
            with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
                for _ in range(chapters_per_thread):
                    engine = EasyOcrEngine(languages=["en"])
                    engine._ensure_reader()

        threads = [
            threading.Thread(target=worker, name=f"ocr-worker-{i}")
            for i in range(thread_count)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total_chapters = chapters_per_thread * thread_count
        # BEFORE fix: 10 readers. AFTER fix: 2 readers (one per thread).
        assert call_count == thread_count, (
            f"Expected {thread_count} Reader creations (one per thread) "
            f"for {total_chapters} chapters, but got {call_count}"
        )
        assert call_count < total_chapters, (
            f"Cache is not working: created {call_count} readers for "
            f"{total_chapters} chapters"
        )


class TestGetOcrEngine:
    def test_tesseract(self) -> None:
        with patch("services.ocr_engine.TesseractEngine") as mock_cls:
            get_ocr_engine("tesseract")
            mock_cls.assert_called_once()

    def test_easyocr(self) -> None:
        with patch("services.ocr_engine.EasyOcrEngine") as mock_cls:
            get_ocr_engine("easyocr")
            mock_cls.assert_called_once()

    def test_unknown(self) -> None:
        with pytest.raises(ValueError, match="Unknown OCR engine"):
            get_ocr_engine("unknown")
