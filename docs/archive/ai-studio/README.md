# Archived — "AI Studio" internal-AI-platform vision

**Status: NOT part of the ManhwaManiacs product roadmap.** Archived 2026-07-11.

These documents describe an abandoned direction: building an *internal* AI
platform inside ManhwaManiacs — a local-model creation studio (ComfyUI /
Ollama), a local LLM stack, an AI knowledge graph, and an in-app manhwa
*creation* pipeline. **None of it was ever implemented**, and it is no longer a
goal. It is preserved here for historical context only; do not treat anything in
this folder as a specification or as work to build.

## What was removed from the live codebase (2026-07-11)

- `backend/routes/ai.py` — the `/ai/chat` stub.
- `backend/services/ollama_service.py` — the Ollama wrapper.
- The `ollama` dependency (`pyproject.toml`, `requirements.txt`).
- Dead AI config keys (`ollama_url`, `comfyui_url`, `default_chat`,
  `default_writer`, `default_reasoner`) in `core/config.py`.
- The frontend `/create` (creation studio) and `/ai` (local-models) placeholder
  pages and their sidebar nav entries.

## What AI *is* in ManhwaManiacs going forward

AI remains a **product capability**, not an internal platform. Planned AI
features will call **external AI APIs** (e.g. the Claude API) when implemented:

- Recommendations · personalized home feed · similar-series suggestions
- Reading / chapter / character / series summaries
- Search improvements · tag generation · metadata enrichment
- Smart collections · continue-reading suggestions

Do **not** build or maintain local models, Ollama/ComfyUI integration, or an
in-app AI studio to deliver these. See `docs/ROADMAP.md` and
`docs/ARCHITECTURE_REVIEW_2026-07-11.md` for the current, authoritative plan.

## Files in this archive

- `CREATION_STUDIO.md` — the in-app manhwa creation studio spec (never built).
- `AI_PIPELINE.md` — the local multi-stage AI pipeline spec; only OCR (stage 3)
  was ever built, and it lives in the real codebase (`services/ocr_pipeline.py`),
  not here.
