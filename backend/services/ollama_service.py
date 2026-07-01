"""Ollama integration.

Thin wrapper around the Ollama client so routes depend on this service,
not on the SDK directly (keeps the transport swappable and testable).
"""

from __future__ import annotations

from functools import lru_cache

from ollama import Client

from core.config import get_settings
from core.errors import AppError


class OllamaService:
    def __init__(self, host: str) -> None:
        self._client = Client(host=host)

    def chat(self, prompt: str, model: str) -> str:
        try:
            response = self._client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001 - surface a clean client-facing error
            raise AppError(
                "Could not reach Ollama. Is it running?",
                code="ollama_unavailable",
                status_code=503,
                details=str(exc),
            ) from exc

        return response["message"]["content"]


@lru_cache
def get_ollama_service() -> OllamaService:
    """FastAPI dependency: a process-wide, lazily-created service instance."""
    return OllamaService(host=get_settings().ollama_url)
