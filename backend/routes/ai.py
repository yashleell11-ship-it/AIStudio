"""AI endpoints (chat, and later: summaries, OCR, enhancement)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.config import get_settings
from services.ollama_service import OllamaService, get_ollama_service

router = APIRouter(prefix="/ai", tags=["ai"])

ServiceDep = Annotated[OllamaService, Depends(get_ollama_service)]


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1)
    model: str | None = None


class ChatResponse(BaseModel):
    model: str
    response: str


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, service: ServiceDep) -> ChatResponse:
    model = body.model or get_settings().default_chat
    return ChatResponse(model=model, response=service.chat(body.prompt, model))
