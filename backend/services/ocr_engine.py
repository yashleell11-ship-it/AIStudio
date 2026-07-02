"""OCR engine abstraction with Tesseract and EasyOCR support.

Engines are designed to be created per-thread for thread-safety.
Lazy imports are used for heavy dependencies (easyocr, torch).

Production improvements:
- Image preprocessing (resize, grayscale, contrast) for accuracy and speed
- Memory-efficient processing with explicit cleanup
- Structured error types for transient vs permanent failures
- Per-recognition timing for metrics
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Thread-local cache for EasyOCR readers
# ------------------------------------------------------------------
# EasyOCR eagerly loads PyTorch models. Creating a new Reader for every
# chapter (and every engine instance) causes the model to reload from disk
# repeatedly, which is extremely slow and memory-intensive.
#
# Solution: cache one Reader per (thread, language_combo) so that a worker
# thread reuses the model across multiple jobs and chapters. The cache is
# cleaned up automatically when the thread dies.
# ------------------------------------------------------------------

_reader_cache = threading.local()


def _get_cached_reader(cache_key: str) -> Any | None:
    """Return a cached EasyOCR reader for the current thread, if any."""
    cache = getattr(_reader_cache, "readers", None)
    if cache is None:
        return None
    return cache.get(cache_key)


def _set_cached_reader(cache_key: str, reader: Any) -> None:
    """Store an EasyOCR reader in the current thread's cache."""
    cache = getattr(_reader_cache, "readers", None)
    if cache is None:
        cache = {}
        setattr(_reader_cache, "readers", cache)
    cache[cache_key] = reader


def _clear_easyocr_cache() -> None:
    """Clear the thread-local EasyOCR reader cache. Primarily used by tests."""
    if hasattr(_reader_cache, "readers"):
        _reader_cache.readers.clear()


def get_easyocr_cache_stats() -> dict[str, Any]:
    """Return diagnostic stats for the thread-local cache."""
    cache = getattr(_reader_cache, "readers", None)
    if cache is None:
        return {"cached_count": 0, "keys": []}
    return {"cached_count": len(cache), "keys": list(cache.keys())}


class OcrError(Exception):
    """Base exception for OCR failures."""

    def __init__(self, message: str, *, is_transient: bool = True) -> None:
        super().__init__(message)
        self.is_transient = is_transient


class OcrEngineNotAvailable(OcrError):
    """Raised when the engine dependency is missing or the binary is not found."""

    def __init__(self, message: str) -> None:
        super().__init__(message, is_transient=False)


class OcrRecognitionError(OcrError):
    """Raised when OCR fails on a specific image."""

    pass


@dataclass
class OcrResult:
    """Result of OCR on a single image."""

    text: str
    confidence: float
    boxes: list[dict[str, Any]] = field(default_factory=list)
    elapsed_ms: float = 0.0


def _preprocess_image(image: "Image.Image", max_size: int = 2000) -> "Image.Image":
    """Preprocess image for better OCR: resize, grayscale, contrast.

    Args:
        image: Input PIL Image.
        max_size: Maximum dimension (width or height) before downscaling.
    """
    from PIL import Image, ImageEnhance

    # Resize if too large (reduces memory and speeds up OCR)
    w, h = image.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        new_w, new_h = int(w * ratio), int(h * ratio)
        image = image.resize((new_w, new_h), Image.LANCZOS)

    # Convert to grayscale for better text contrast
    if image.mode != "L":
        image = image.convert("L")

    # Mild contrast enhancement
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.2)

    return image


class OcrEngine(ABC):
    """Abstract base for OCR engines."""

    @abstractmethod
    def recognize(self, image: "Image.Image", *, preprocess: bool = True) -> OcrResult:
        """Run OCR on a PIL Image and return extracted text + metadata.

        Args:
            image: PIL Image to process.
            preprocess: Whether to apply image preprocessing (resize, grayscale,
                contrast). Defaults to True.
        """
        ...


class TesseractEngine(OcrEngine):
    """Tesseract-based OCR engine.

    Requires the ``pytesseract`` Python package and the tesseract binary.
    """

    def __init__(self, language: str | None = None) -> None:
        from core.config import get_settings

        self._language = language or get_settings().ocr_language
        try:
            import pytesseract

            self._pytesseract = pytesseract
            # Verify the binary is actually callable
            self._pytesseract.get_tesseract_version()
        except ImportError as exc:
            raise OcrEngineNotAvailable(
                "pytesseract is not installed. Add it to dependencies and install "
                "the Tesseract OCR binary."
            ) from exc
        except Exception as exc:
            raise OcrEngineNotAvailable(
                f"Tesseract binary is not available: {exc}"
            ) from exc

    def recognize(self, image: "Image.Image", *, preprocess: bool = True) -> OcrResult:
        from PIL import Image

        if not isinstance(image, Image.Image):
            raise TypeError("Expected PIL Image instance")

        started = time.perf_counter()
        try:
            if preprocess:
                image = _preprocess_image(image)

            data = self._pytesseract.image_to_data(
                image,
                lang=self._language,
                output_type=self._pytesseract.Output.DICT,
            )

            text_parts: list[str] = []
            confidences: list[int] = []
            boxes: list[dict[str, Any]] = []

            for i in range(len(data["text"])):
                conf = int(data["conf"][i])
                text_block = data["text"][i].strip()
                if conf > 0 and text_block:
                    text_parts.append(text_block)
                    confidences.append(conf)
                    boxes.append(
                        {
                            "x": data["left"][i],
                            "y": data["top"][i],
                            "w": data["width"][i],
                            "h": data["height"][i],
                            "conf": conf,
                        }
                    )

            full_text = " ".join(text_parts)
            avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.0
            elapsed_ms = (time.perf_counter() - started) * 1000
            return OcrResult(
                text=full_text,
                confidence=avg_conf / 100.0,
                boxes=boxes,
                elapsed_ms=elapsed_ms,
            )
        except Exception as exc:
            raise OcrRecognitionError(f"Tesseract recognition failed: {exc}")


class EasyOcrEngine(OcrEngine):
    """EasyOCR-based OCR engine.

    Requires the ``easyocr`` package.  The underlying ``Reader`` (which eagerly
    loads PyTorch models) is cached **per worker thread** so that multiple
    ``EasyOcrEngine`` instances created on the same thread share the same model.
    This avoids reloading the model for every chapter/job.
    """

    def __init__(self, languages: list[str] | None = None) -> None:
        self._languages = languages or ["en"]
        self._cache_key = "reader_" + "_".join(sorted(self._languages))

    def _ensure_reader(self) -> Any:
        """Return a cached Reader for this thread, creating one if needed."""
        reader = _get_cached_reader(self._cache_key)
        if reader is not None:
            return reader

        try:
            import easyocr
        except ImportError as exc:
            raise OcrEngineNotAvailable(
                "easyocr is not installed. Run: pip install easyocr"
            ) from exc

        reader = easyocr.Reader(self._languages)
        _set_cached_reader(self._cache_key, reader)
        logger.info(
            "EasyOCR Reader loaded for languages %s (thread %s)",
            self._languages,
            threading.current_thread().name,
        )
        return reader

    def recognize(self, image: "Image.Image", *, preprocess: bool = True) -> OcrResult:
        from PIL import Image

        if not isinstance(image, Image.Image):
            raise TypeError("Expected PIL Image instance")

        started = time.perf_counter()
        try:
            if preprocess:
                image = _preprocess_image(image)

            # EasyOCR accepts numpy arrays, but we keep numpy optional for the backend
            # because EasyOCR is an optional engine. Most unit tests mock EasyOCR and
            # do not install heavy deps.
            results = self._ensure_reader().readtext(image)

            text_parts: list[str] = []
            boxes: list[dict[str, Any]] = []
            confidences: list[float] = []

            for result in results:
                # result format: (bbox, text, confidence)
                bbox, text, conf = result
                text_parts.append(text)
                confidences.append(conf)
                boxes.append({"bbox": bbox, "conf": conf})

            full_text = " ".join(text_parts)
            avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.0
            elapsed_ms = (time.perf_counter() - started) * 1000
            return OcrResult(
                text=full_text,
                confidence=avg_conf,
                boxes=boxes,
                elapsed_ms=elapsed_ms,
            )
        except Exception as exc:
            raise OcrRecognitionError(f"EasyOCR recognition failed: {exc}")


def get_ocr_engine(engine_name: str | None = None, **kwargs: Any) -> OcrEngine:
    """Factory that returns an engine instance by name.

    The engine is created fresh so it can be safely used in a worker thread.
    """
    from core.config import get_settings

    name = (engine_name or get_settings().ocr_engine).lower()
    if name == "tesseract":
        return TesseractEngine(**kwargs)
    if name == "easyocr":
        return EasyOcrEngine(**kwargs)
    raise ValueError(f"Unknown OCR engine: {name}")
