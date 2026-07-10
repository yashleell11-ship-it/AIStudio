# AIStudio — Complete AI Processing Pipeline

**Status:** Canonical reference. All AI service and worker code must match this design.
**Cross-references:** [ARCHITECTURE.md](ARCHITECTURE.md) · [DATABASE.md](DATABASE.md) · [API.md](API.md)

---

## 1. Overview

The AI pipeline transforms raw image files into a fully indexed, queryable knowledge
base — dialogue extracted, characters profiled, timelines built, lore catalogued,
and every page semantically searchable.

```
Folder Scanner → Image Loader → OCR → Metadata Extraction → Character Detection →
Relationship Extraction → Timeline Generation → World Memory → Embeddings →
Vector Database → Summary Generation → Semantic Search → Chat Context →
Recommendations → Caching → Background Workers → Re-indexing → Incremental Updates
```

All pipeline stages run as background tasks. They never block the HTTP server.
The user can read and navigate their library while any stage runs.

### Design constraints

- **Single GPU.** All Ollama stages serialize through one process. Concurrency is
  per-stage-type: at most one OCR job, one embed job, one summary job, and one
  knowledge-extraction job run simultaneously.
- **Failure isolation.** A failure on page N must not stop processing on page N+1.
  Every per-item stage (page, chapter, chunk) is independently retried.
- **User edits are sacred.** Any row with `is_user_edited = 1` is never overwritten
  by a pipeline re-run. AI output is always a starting point, not a replacement.
- **Incremental by default.** Every stage checks whether its output already exists
  before processing. Re-runs are opt-in, not implicit.
- **No external services.** The entire pipeline runs locally: Ollama for LLM/vision,
  ComfyUI for image generation, NumPy for vector similarity.

### Worker priority order (highest first)

```
4 — scan (blocking the user from seeing content)
3 — thumbnail (blocking cover display)
2 — ocr (required before all AI stages)
1 — embed (required before semantic search)
0 — summarize, knowledge, timeline, world
```

---

## 2. Stage 1 — Folder Scanner

### Purpose

Discover all series, chapters, and pages in a registered library root and upsert
them into the database. The user's files are never copied or modified.

### Input

- One or more library root paths (`libraries.root_path`)
- Optional: a single subdirectory path for incremental import

### Output

Rows created or updated in: `series`, `volumes`, `chapters`, `pages`, `import_history`.
`series.total_chapters` and `series.total_pages` denormalized counts updated.

### Algorithm

1. Walk the root path using `os.scandir()` recursively (faster than `os.walk()`
   for very deep trees; avoids storing the full tree in memory).
2. Match subdirectories against known folder patterns to distinguish
   series-level directories from chapter-level directories.
3. Detect chapter source type by file contents:
   - `.cbz` / `.cbr` → archive type
   - `.pdf` → PDF type
   - Directory containing only images → folder type
4. Compute `chapter.sort_key` as a zero-padded number string: `f"{number:08.3f}"`.
   This gives stable lexicographic sort without CAST() in SQL.
5. Upsert: `INSERT OR IGNORE` then `UPDATE` if `scanned_at < file mtime`.
6. Detect deletions: series present in DB but not found on disk get `deleted_at`
   set to now (soft delete).
7. Write one `import_history` row with `series_added`, `series_updated`,
   `chapters_added`, `pages_added` counts.

### Database tables

Read: `libraries`, `series`, `chapters`, `pages`
Write: `series`, `volumes`, `chapters`, `pages`, `import_history`, `background_tasks`

### Performance considerations

- Batch DB inserts in groups of 500 rows using `executemany`. One transaction per
  chapter.
- Skip hash computation during the initial scan. SHA-256 is computed lazily when
  incremental update needs change detection.
- For a library of 100,000 chapters (average 50 pages each), expect 5M page rows.
  The scan itself (no hashing) should complete in under 10 minutes on a local SSD.
- Two library roots can scan in parallel (separate threads), as they write to
  different series rows.

### Failure handling

- `PermissionError` on a subdirectory: log and skip that subtree; continue the rest.
- `UnicodeDecodeError` in filename: log and skip that file.
- `sqlite3.OperationalError` (disk full): abort the scan, mark `import_history`
  as failed, surface the error in the task status.
- On resume after crash: the scanner is idempotent. Re-running inserts nothing
  for already-scanned paths.

### Background job requirements

- Task type: `scan`
- Priority: 4 (highest)
- Single worker per library root (no parallelism within one root)
- Reports progress as `pages_scanned / estimated_total` via `background_tasks.progress_pct`

### GPU usage

None.

### Future scalability

- At 1M+ series, replace the full directory walk with a file system watcher
  (Stage 18) so scans are event-driven, not periodic.
- For network shares (NAS), use smb2 or rclone mount; the scanner logic is unchanged.

---

## 3. Stage 2 — Image Loader

### Purpose

Validate and measure every page image: confirm the file exists and is readable,
record pixel dimensions, detect MIME type. This is a prerequisite for the reader
(to compute page aspect ratios) and for the OCR worker (to pass correct image
dimensions to the model).

### Input

`pages` rows where `width IS NULL` (not yet measured).

### Output

`pages.width`, `pages.height`, `pages.mime_type`, `pages.file_size_bytes` updated.

### Algorithm

For each unmeasured page:
1. Open the image with `PIL.Image.open()` using `Image.verify()` (validates
   without full decode) then re-open to read `.size`.
2. For archive pages (`source_type = 'cbz'`): extract the single entry from the
   ZIP in memory, measure, then discard the bytes.
3. For PDF pages: use PyMuPDF to render a 1×1 pixmap and read its dimensions.
4. Update the `pages` row in a batch flush every 200 rows.

### Database tables

Read: `pages`, `chapters`
Write: `pages`

### Performance considerations

- CPU-bound, not GPU-bound. Run in a thread pool (4 threads).
- `PIL.Image.open()` without `.load()` reads only the image header — very fast.
- For a 5M page library, expect ~8 hours at 4 threads (roughly 700 pages/sec).
  This runs as a background task, never on the critical path of the reader.
- The reader can serve pages before measurement completes; width/height = null is
  handled with a placeholder `aspect-ratio: auto` in CSS.

### Failure handling

- Corrupt image (truncated, wrong header): mark page with `mime_type = 'error'`,
  log, continue.
- Archive entry missing: log, continue. The reader will hit `image_file_missing`
  later when trying to serve it.
- No retry — image corruption is permanent until the user replaces the file.

### Background job requirements

- Task type: `thumbnail` (shares priority with cover generation)
- Priority: 3
- Runs immediately after scan for newly discovered pages

### GPU usage

None.

### Future scalability

Scale by adding more CPUs; this stage is embarrassingly parallel per-chapter.

---

## 4. Stage 3 — OCR

### Purpose

Extract the raw text from every manga/manhwa page. Text is the foundation for
search, summaries, chat, character detection, and all downstream AI stages.
Nothing downstream can run until OCR is complete.

### Input

`pages` rows for a chapter where no corresponding `ocr_pages` row exists.
Raw image bytes (from disk, ZIP extraction, or PDF render).

### Output

One `ocr_pages` row per page.
FTS5 index `ocr_fts` updated via trigger (automatic, no code needed).
`chapter_ocr_status.ocr_pages_done` incremented after each page.
`series_ai_status.ocr_pct` updated after each chapter completes.

### Algorithm

For each unprocessed page:
1. Load the image. For CBZ: extract from ZIP. For PDF: render to PNG via PyMuPDF.
2. Call Ollama vision model (e.g., `minicpm-v:8b` or `llava:13b`) with the image
   plus a system prompt instructing it to extract all dialogue, narration, and
   sound effects in reading order. Return plain text only.
3. Count words (`len(text.split())`). If word count < 5, the page is likely
   full-art with no text — set `text_content = ''`, `confidence = 0.0`.
4. Insert into `ocr_pages`. The FTS5 trigger fires automatically.
5. Update `chapter_ocr_status.ocr_pages_done += 1`.
6. After all pages in a chapter: set `chapter_ocr_status.is_complete = 1`.
7. After all chapters in a series: update `series_ai_status.ocr_pct = 100.0`,
   `series_ai_status.ocr_completed_at = now`.

### Database tables

Read: `pages`, `chapters`, `series`
Write: `ocr_pages`, `chapter_ocr_status`, `series_ai_status`, `ocr_fts` (via trigger)

### Performance considerations

- **This is the most expensive stage.** A vision model call per page at ~2 seconds/call
  means 100,000 pages = 55 hours. Target: schedule and let it run overnight.
- Process at most 1 image at a time through Ollama (Ollama itself does not batch
  vision inputs efficiently). Use a thread that feeds Ollama one request at a time.
- Keep pages in chapter order to benefit from Ollama's KV cache (same model,
  similar context window prefixes within a chapter).
- OCR progress is streamed via WebSocket so the user can watch it complete.
- At 5M pages: OCR is a multi-day background job. Users should be warned that
  AI features are gated on OCR completion.

### Failure handling

- Ollama timeout (>30 seconds): mark page retry count +1, move to back of queue.
  Retry up to 3 times, then set a failed flag and skip.
- Ollama process crash: detect via connection error; pause the OCR queue for 60
  seconds, then retry. Do not mark pages as failed — Ollama may come back up.
- Partial chapter OCR: perfectly fine. `chapter_ocr_status.is_complete` stays `0`
  until all pages are done. The user can still read the chapter; only AI features
  are gated.
- Model change by user: existing `ocr_pages` rows remain. Re-indexing is opt-in
  (Stage 17).

### Background job requirements

- Task type: `ocr`
- Priority: 2
- Concurrency: exactly 1 OCR worker at a time (single GPU)
- Progress: page count reported to `background_tasks.progress_pct`

### GPU usage

**HIGH.** Vision model at 8B parameters requires 6–10 GB VRAM. This is the
dominant GPU consumer. All other AI stages defer to this worker.

### Future scalability

- Multiple GPUs: run one OCR worker per GPU with separate task queues.
- Cloud burst: route batches to a remote GPU server during peak processing.
- Dedicated OCR model (e.g., GOT-OCR2, manga-specific fine-tune) for higher
  accuracy on Japanese/Korean text with faster throughput.

---

## 5. Stage 4 — Metadata Extraction

### Purpose

Auto-classify a series: detect genre, audience, content rating, and generate a
description. Reduces the manual metadata editing burden for large libraries.

### Input

OCR text from the first 5 chapters of the series (or all chapters if fewer than 5).
`series` row (to check which fields already have values).

### Output

Updates to `series.description`, `series.content_rating`.
New `series_tags` rows for detected genres and themes.
New `ai_summaries` row with `summary_type = 'metadata'` containing the raw
LLM classification response (for audit purposes).

### Algorithm

1. Fetch OCR text for the first 5 chapters, concatenate up to 8,000 tokens.
2. Call the configured `default_writer` model with a structured prompt that asks for:
   - Genre tags (pick from fixed vocabulary matching the tags table)
   - Content rating (`safe` | `suggestive` | `adult`)
   - One-paragraph description (100–200 words)
   - Year estimate (if detectable from art style/references)
3. Parse the JSON response. Insert/upsert `series_tags` rows with
   `is_ai_generated = 1`, `confidence` from model output.
4. Only update `series` fields that the user has not manually set
   (check `series.updated_at > series.created_at` as a proxy).

### Database tables

Read: `ocr_pages`, `pages`, `chapters`, `series`
Write: `series`, `series_tags`, `ai_summaries`

### Performance considerations

- Text-only model call; fast (~5 seconds per series).
- Run after OCR of the first 5 chapters, not after the whole series.
  The user sees metadata almost immediately.

### Failure handling

- Malformed JSON from LLM: retry with a stricter JSON-mode prompt. If still failing,
  log and skip — metadata is non-critical, user can fill in manually.
- Unknown tag name in LLM response: fuzzy-match against the `tags` table. If no
  match, create a new tag rather than silently dropping it.

### Background job requirements

- Task type: `knowledge` (shares queue with other extraction tasks)
- Priority: 0
- Runs after OCR of first chapter batch

### GPU usage

**MODERATE.** Text-only inference on a 7–13B model; typically 3–5 seconds per series.

### Future scalability

- Fine-tune a classification model on a curated manga dataset for faster, more
  accurate genre detection without a general-purpose LLM.

---

## 6. Stage 5 — Character Detection

### Purpose

Build the initial character roster: names, roles, and first appearances.
Characters are the primary entry point for the knowledge graph.

### Input

All `ocr_pages` rows for a series. `chapters` table for appearance tracking.

### Output

`characters` rows (name, role, description stub).
`character_aliases` rows (common names and nicknames).
`character_appearances` rows (chapter_id, page_number for first appearance).

### Algorithm

1. Concatenate OCR text, partitioned by chapter (to track first appearances).
2. Pass chunks of ~8,000 tokens to the `default_reasoner` model with a prompt that
   asks: "List every named character you can identify. For each: canonical name,
   any aliases mentioned, their role (protagonist/antagonist/supporting/minor),
   and the approximate chapter where they first appear."
3. Deduplicate output: merge characters with the same canonical name.
4. For each identified character, run a second pass on the chapter where they first
   appear to find the specific page number (search OCR text for the name).
5. Insert `characters` rows with `is_ai_generated = 1`.
6. Insert `character_aliases` for each alias.
7. Insert `character_appearances` for first-appearance page.

### Database tables

Read: `ocr_pages`, `chapters`, `pages`
Write: `characters`, `character_aliases`, `character_appearances`, `series_ai_status`

### Performance considerations

- Run in batches of 10 chapters to keep context windows manageable.
- First-appearance search is a SQL LIKE query on `ocr_pages.text_content` — fast
  with the FTS5 index rather than LIKE.
- A 179-chapter series processes in roughly 15–30 minutes.

### Failure handling

- LLM invents a character name not in the text: the user will see it and can delete.
  AI output is always marked `is_ai_generated = 1` so it's easy to audit.
- Character appears under different names across chapters (common in manhwa):
  the alias system handles this. User can merge characters manually.
- Missing character (LLM missed someone): user adds them via the Knowledge page.

### Background job requirements

- Task type: `knowledge`
- Priority: 0
- Requires: OCR complete (`series_ai_status.ocr_pct = 100.0`)

### GPU usage

**MODERATE.** Reasoning model (e.g., `qwen3:30b`) at 30B parameters.
Expect 5–15 seconds per batch.

### Future scalability

- Train a NER (Named Entity Recognition) model specifically on manhwa OCR text for
  faster, cheaper character detection without a general LLM.
- Visual character detection (face clustering across pages) as a separate enhancement.

---

## 7. Stage 6 — Relationship Extraction

### Purpose

Build a relationship graph between characters: friendships, rivalries, family bonds,
political alliances. Used for the Knowledge Graph visual and for enriching chat context.

### Input

`characters` table (all characters for this series).
`ocr_pages` text, chapter-by-chapter.

### Output

`character_relationships` rows.

### Algorithm

1. Build a list of all character names (canonical + aliases) as a lookup set.
2. For each chapter:
   a. Find OCR text. Filter out pages where none of the character names appear.
   b. For remaining pages, pass to the `default_reasoner` with a prompt: "Given
      these characters: [list]. Extract all relationships you can infer from the
      following dialogue. Return pairs with relationship type and a one-sentence
      description."
3. Aggregate results across all chapters. For each extracted pair:
   a. Normalize so `character_a_id < character_b_id` (canonical ordering).
   b. If a relationship already exists between this pair: update `description`
      with the more recent version (unless `is_user_edited = 1`).
   c. Otherwise: insert new row.

### Database tables

Read: `characters`, `character_aliases`, `ocr_pages`, `chapters`
Write: `character_relationships`

### Performance considerations

- Filter pages before passing to LLM: only pass pages where at least 2 known
  character names co-occur. This cuts LLM calls by ~60% for dialogue-heavy series.
- Each chapter is one LLM call. A 179-chapter series = 179 calls.

### Failure handling

- LLM invents a relationship not supported by the text: user edits.
- LLM returns character names that don't match canonical names: fuzzy-match against
  the alias table. If still no match, skip that relationship and log it.

### Background job requirements

- Task type: `knowledge`
- Priority: 0
- Requires: Character detection complete

### GPU usage

**MODERATE.** Same as character detection.

### Future scalability

Build a dedicated relationship extraction model fine-tuned on manga/manhwa
character interactions. Should be a smaller, faster model than the general reasoner.

---

## 8. Stage 7 — Timeline Generation

### Purpose

Build a chronological event log of the story. Events link characters, chapters, and
locations. The timeline is the primary output of the AI "story intelligence" feature.

### Input

`ai_summaries` (chapter summaries — must exist before this stage runs).
`characters` table (for linking characters to events).

### Output

`timeline_events` rows.
`timeline_event_characters` rows.

### Algorithm

1. Load all chapter summaries in order.
2. Pass batches of 10 summaries (with chapter numbers) to the `default_reasoner`:
   "Extract the 3–7 most significant plot events from these chapters. For each event:
   title, one-sentence description, event type (plot_point/revelation/battle/death/
   reunion/timeskip), sequence_order (float, matching chapter number), characters
   involved."
3. Aggregate events from all batches, sort by `sequence_order`.
4. For each event:
   a. Insert `timeline_events` row.
   b. Match character names to `characters` table; insert `timeline_event_characters`.
5. Set `is_spoiler = 1` for events from chapters the user has not yet read
   (cross-reference `reading_progress.current_chapter_id`).

### Database tables

Read: `ai_summaries`, `characters`, `chapters`, `reading_progress`
Write: `timeline_events`, `timeline_event_characters`

### Performance considerations

- Requires summaries, so this stage runs after Stage 11.
- One LLM call per 10-chapter batch. A 179-chapter series = ~18 calls.
- Total generation time: 5–15 minutes.

### Failure handling

- Batch fails: retry that batch up to 3 times. If still failing, mark those
  chapters as skipped and continue with the next batch.
- Timeline events out of sequence: `sequence_order` is a float, so events can
  always be inserted between existing ones without renumbering.

### Background job requirements

- Task type: `knowledge`
- Priority: 0
- Requires: Summary generation complete

### GPU usage

**HIGH.** The reasoning model processes many summaries at once with long context.

### Future scalability

Long-context models (128K+ tokens) allow processing the entire chapter summary
list in a single call, producing more coherent timelines. Scale as model quality improves.

---

## 9. Stage 8 — World Memory

### Purpose

Extract the series "universe": locations, factions/organizations, magic/power systems,
historical events, and world-specific rules. This is the lore database.

### Input

`ai_summaries` (all chapter summaries).
`ocr_pages` (for specific terminology that may not appear in summaries).

### Output

`world_locations` rows.
`world_factions` rows.
`character_factions` rows.
`world_lore` rows.

### Algorithm

1. Concatenate all series-level summaries plus the series description.
2. Pass to `default_reasoner` with a structured prompt requesting:
   - Named locations (type: dungeon/city/realm/building/region)
   - Organizations/factions (type: guild/government/clan/system)
   - Power systems and special rules (type: power_system/rule/history/prophecy)
3. For factions: run a second pass on character OCR context to link characters to
   their factions (populates `character_factions`).
4. For locations: detect parent/child relationships ("Jeju Island" → "Jeju Island
   S-Rank Gate") to populate `parent_id`.

### Database tables

Read: `ai_summaries`, `ocr_pages`, `characters`
Write: `world_locations`, `world_factions`, `character_factions`, `world_lore`

### Performance considerations

- Typically 3–5 LLM calls per series (one per category plus linking passes).
- Total: ~5 minutes per series.

### Failure handling

- Missing location/faction: user adds manually.
- Incorrect parent/child hierarchy: user reorders in the Knowledge UI.

### Background job requirements

- Task type: `knowledge`
- Priority: 0
- Requires: Summary generation complete, Character detection complete

### GPU usage

**MODERATE.** Long-context single call using series-level summaries.

### Future scalability

Fine-tuned world-extraction model for faster results without a general reasoning LLM.

---

## 10. Stage 9 — Embeddings

### Purpose

Create dense vector representations (embeddings) of all text content. Embeddings
enable semantic search ("find pages where Jin-woo feels despair") and
recommendation ("find series similar to this one").

### Input

Text chunks from:
- `ocr_pages.text_content` (panel dialogue)
- `ai_summaries.content` (chapter and series summaries)
- `characters.description` + `characters.arc_summary`
- `world_lore.content`

### Output

`embedding_chunks` rows (source reference + text chunk).
`embeddings` rows (binary vector blob).

### Chunking strategy

| Source | Chunk size | Overlap |
|--------|------------|---------|
| OCR page | one page = one chunk | none |
| Chapter summary | whole summary = one chunk | none |
| Series summary | whole summary = one chunk | none |
| Long character description | 512 tokens | 64 tokens |
| Long lore entry | 512 tokens | 64 tokens |

Rationale: pages are already small (typically < 200 tokens). Summaries are
short by design. Only character profiles and lore entries may need splitting.

### Algorithm

1. For each source (OCR, summary, character, lore):
   a. Fetch all rows not yet in `embedding_chunks`.
   b. Chunk the text. Insert `embedding_chunks` rows.
2. For each `embedding_chunks` row not yet in `embeddings`:
   a. Call Ollama with the embedding model (e.g., `nomic-embed-text`).
   b. Receive a float32 vector (e.g., 768 dimensions).
   c. Serialize to bytes (`numpy.array(vector, dtype=float32).tobytes()`).
   d. Insert `embeddings` row with `vector = <bytes>`, `dimensions = 768`,
      `model = 'nomic-embed-text'`.
3. After all chunks for a series: update `series_ai_status.embed_pct = 100.0`,
   `embed_completed_at = now`.

### Database tables

Read: `ocr_pages`, `ai_summaries`, `characters`, `world_lore`, `embedding_chunks`
Write: `embedding_chunks`, `embeddings`, `series_ai_status`

### Performance considerations

- Embedding is much faster than OCR. A typical embedding model processes
  ~1000 tokens/second → a 10,000-token chapter takes ~10 seconds.
- Batch up to 32 chunks per Ollama API call for throughput.
- A 5M-page library with 20M total chunks at 768 dimensions = 60 GB of binary data.
  This will exceed SQLite's practical limits. **Plan for PostgreSQL + pgvector by
  ~500K chunks.** The migration is a connection-string change plus BLOB → VECTOR(768).

### Failure handling

- Ollama embedding timeout: retry chunk up to 3 times, then mark as failed and
  skip. Semantic search degrades gracefully without that chunk.
- Disk full: abort embedding run, surface error. Partially embedded series still
  supports FTS search.

### Background job requirements

- Task type: `embed`
- Priority: 1 (just below OCR)
- Concurrency: 1 embed worker (single GPU, but embedding is less VRAM-intensive)
- Batch size: 32 chunks per Ollama call

### GPU usage

**LOW-MODERATE.** Embedding models (e.g., `nomic-embed-text` at 137M params) need
~1 GB VRAM. Can run concurrently with OCR on high-VRAM GPUs but is serialized
by default to avoid memory pressure.

### Future scalability

- pgvector with HNSW index supports ~10M vectors with sub-10ms query latency.
- Beyond that: Qdrant or Milvus as a dedicated vector database sidecar.
- Embedding model upgrade (larger dimensions, better quality) requires re-embedding.
  The `embedding_chunks` table preserves text, so only `embeddings` rows need to
  be deleted and regenerated.

---

## 11. Stage 10 — Vector Database

This is not a separate processing stage; it is the query-time component of Stage 9.

### Purpose

Given a query vector, find the top-K most similar embedding chunks.

### Current implementation (SQLite, < 500K embeddings)

```python
import numpy as np

def cosine_search(conn, query_vector: list[float], top_k: int = 20,
                  series_id: int | None = None) -> list[dict]:
    # Load all vectors (or per-series subset) into NumPy
    rows = conn.execute(
        "SELECT e.id, e.chunk_id, e.vector, ec.series_id "
        "FROM embeddings e JOIN embedding_chunks ec ON e.chunk_id = ec.id "
        + ("WHERE ec.series_id = ?" if series_id else ""),
        (series_id,) if series_id else ()
    ).fetchall()

    vectors = np.frombuffer(b"".join(r["vector"] for r in rows),
                            dtype=np.float32).reshape(len(rows), -1)
    q = np.array(query_vector, dtype=np.float32)
    q /= np.linalg.norm(q)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    scores = vectors @ q
    top_idx = np.argpartition(scores, -top_k)[-top_k:]
    top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]
    return [{"chunk_id": rows[i]["chunk_id"], "score": float(scores[i])} for i in top_idx]
```

### Performance

| Embedding count | Query latency (NumPy, CPU) |
|-----------------|---------------------------|
| 10K | < 1 ms |
| 100K | ~10 ms |
| 500K | ~50 ms |
| 1M | ~100 ms (approaching limit) |

At > 500K embeddings, migrate to PostgreSQL + pgvector:

```sql
-- PostgreSQL only
ALTER TABLE embeddings ALTER COLUMN vector TYPE VECTOR(768);
CREATE INDEX idx_embeddings_hnsw ON embeddings
    USING hnsw (vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);
```

Query time with HNSW at 10M vectors: < 5 ms (approximate nearest neighbor).

### Failure handling

- If no embeddings exist for a series: return empty results. The API returns
  `embeddings_not_ready` (409) so the frontend can show a helpful message.

---

## 12. Stage 11 — Summary Generation

### Purpose

Generate human-readable summaries of each chapter and a series-level synopsis.
Summaries power the timeline (Stage 7), world extraction (Stage 8), and chat
context (Stage 13). They are also displayed directly in the reader and knowledge UI.

### Input

`ocr_pages.text_content` for a chapter (concatenated in page order).

### Output

One `ai_summaries` row per chapter (`summary_type = 'chapter'`).
One `ai_summaries` row for the series (`summary_type = 'series'`, generated from
chapter summaries).

### Algorithm

**Chapter summaries (per chapter):**
1. Concatenate OCR text for all pages in the chapter.
2. Truncate to model context limit (approximately 6,000 tokens for a standard chapter;
   if longer, use the first and last 3,000 tokens to capture setup and resolution).
3. Call `default_writer` model:
   "Summarize this manga chapter in 2–4 sentences. Focus on plot events, character
   actions, and revelations. Do not editorialize. Do not include spoiler warnings.
   Plain text only."
4. Insert `ai_summaries` row (`is_ai_generated = 1`, `is_user_edited = 0`).

**Series summary (generated after all chapter summaries exist):**
1. Concatenate all chapter summaries, in order.
2. If total tokens > 12,000: use the first 5 and last 5 chapter summaries as
   bookmarks, with a middle section of every 10th chapter.
3. Call `default_writer` model:
   "Write a 200-word synopsis of this manga series based on chapter summaries.
   Include the core premise, main character arc, and tone. Avoid spoilers past
   chapter N." (N = user's current chapter or last chapter, depending on setting.)

### Database tables

Read: `ocr_pages`, `pages`, `chapters`, `series`
Write: `ai_summaries`, `series_ai_status`

### Performance considerations

- Target: 1 summary per 5–10 seconds with a mid-size model.
- A 179-chapter series: 15–30 minutes for all chapter summaries.
- Runs concurrently with embedding (different GPU resource: embed uses embedding
  model, summary uses writer model) but serializes through Ollama by default.

### Failure handling

- Chapter has no OCR text (all art pages): generate summary from just the chapter
  number and position: "Chapter N appears to be an art-only or action chapter
  with minimal dialogue."
- Ollama timeout: retry 3 times with exponential backoff (5s, 15s, 45s). On
  final failure: mark `background_tasks` with error; skip chapter.
- User has manually edited a summary (`is_user_edited = 1`): never overwrite.

### Background job requirements

- Task type: `summarize`
- Priority: 0
- Requires: OCR complete
- Concurrency: 1 summary worker (serialized with OCR through Ollama)

### GPU usage

**MODERATE.** Writer model (e.g., `llama3.3:70b`) needs 24–40 GB VRAM for full
parameter; use a quantized version (Q4_K_M, ~20 GB) in practice.

### Future scalability

- Tiered summary: quick summaries with a small model (7B), deeper ones on demand
  with the large model. Surface quality difference in UI.
- Multi-level summaries: arc-level (every N chapters), volume-level, series-level.
  All stored as different `summary_type` values in `ai_summaries`.

---

## 13. Stage 12 — Semantic Search

This is a query-time stage, not a background job.

### Purpose

Find content matching a natural language query using vector similarity.
Complements FTS5 (exact word match) with meaning-based retrieval.

### Input

User text query string. Optional: `series_id` filter.

### Output

Ranked list of matching `embedding_chunks` with source context (page, chapter,
series). Returned via `GET /search/semantic` or as part of `GET /search?semantic=true`.

### Algorithm

1. Embed the user's query using the same embedding model as Stage 9
   (`nomic-embed-text`). One Ollama call (~200 ms).
2. Run cosine similarity search (Stage 10 algorithm) against all embeddings,
   filtered by `series_id` if provided.
3. Fetch the source rows for the top-K results:
   - For `source_type = 'ocr_page'`: fetch `ocr_pages` + `pages` + `chapters`
     for image URL and page number.
   - For `source_type = 'summary'`: fetch `ai_summaries` + `chapters`.
   - For `source_type = 'character'`: fetch `characters`.
   - For `source_type = 'lore'`: fetch `world_lore`.
4. Re-rank using a weighted combination: vector similarity (70%) + FTS5 BM25
   score (30%) if the query terms also appear in the FTS index.
5. Return top-20 results.

### Performance targets

- Query embedding: 200 ms
- Vector search (per-series, 50K embeddings): < 20 ms
- Total end-to-end: < 500 ms

### Failure handling

- No embeddings for series: return `embeddings_not_ready` (409).
- Ollama unavailable for query embedding: fallback to FTS-only search.
  Return a warning flag in the response: `"semantic_unavailable": true`.

### GPU usage

**LOW.** Only the query embedding call uses GPU. The similarity computation is CPU (NumPy).

---

## 14. Stage 13 — Chat Context

This is a query-time stage invoked by `POST /ai/chat/sessions/{id}/messages`.

### Purpose

Assemble the optimal context window for answering a user's question about a series.
The context must respect the spoiler gate (don't reveal content past the user's
current reading position) while providing enough grounding for the AI to give
accurate, specific answers.

### Input

- User's message (text)
- Session's `context_chapter_id` (spoiler gate — null = full series access)
- Session's conversation history (for multi-turn coherence)
- Series ID

### Output

Streamed text response (SSE or WebSocket). One `ai_chat_messages` row for user
turn; one for assistant turn (written after stream completes).

### Algorithm

1. **Embed the query.** One call to the embedding model (~200 ms).

2. **Retrieve relevant chunks.** Cosine search over the series embeddings, with
   an additional filter: if `context_chapter_id` is set, only include chunks
   from chapters with `number ≤ context_chapter.number`.

3. **Assemble base context:**
   - Character summaries for all named characters mentioned in the query
     (match against `character_aliases`)
   - Series description
   - Chapter summary for the current chapter (if the user is mid-chapter)

4. **Build context window (token budget: ~12,000 tokens):**
   - Reserve 2,000 tokens for the conversation history (last 6 turns)
   - Reserve 1,000 tokens for the system prompt
   - Reserve 500 tokens for the AI response headroom
   - Fill remaining 8,500 tokens with retrieved chunks, sorted by similarity score.
     Truncate gracefully if over budget.

5. **System prompt** (condensed):
   ```
   You are an assistant for the series "{title}". Answer questions using only
   the provided context. If you don't know something, say so. Do not reveal
   events beyond chapter {context_chapter_id}.
   ```

6. **Call Ollama** with the assembled messages array. Stream the response via SSE.

7. **After stream completes:** write both `ai_chat_messages` rows (user + assistant).
   Increment `ai_chat_messages.tokens_used`.

### Database tables

Read: `ai_chat_sessions`, `ai_chat_messages`, `series`, `characters`,
      `character_aliases`, `ai_summaries`, `embeddings`, `embedding_chunks`,
      `ocr_pages`, `chapters`
Write: `ai_chat_messages`

### Performance considerations

- Context assembly: < 300 ms (all fast DB queries + one vector search)
- Time to first token: < 2 seconds (model-dependent)
- Streaming: 50–100 ms between tokens, perceived as instant by users
- Total latency per message: 2–15 seconds depending on response length and model

### Failure handling

- Ollama disconnects mid-stream: write an error `ai_chat_messages` row
  (`is_error = 1`), close the SSE stream with an error event. User sees the
  partial response and a "Connection lost" indicator.
- Context assembly fails (DB error): return 500 before starting the stream.

### GPU usage

**HIGH during response generation.** Uses the `default_reasoner` or user-selected
chat model (e.g., `qwen3:30b`). This blocks all other Ollama usage until the
response is complete.

---

## 15. Stage 14 — Recommendations

### Purpose

Suggest similar series from the user's own library, based on content similarity
(not user behavior — we have no external user data). Pure local computation.

### Input

All series embeddings (specifically the chapter-summary embeddings, which capture
story tone and themes better than OCR dialogue).

### Output

Ordered list of series IDs with similarity scores. Not stored in DB — computed
on demand and cached in application memory for 1 hour.

### Algorithm

For a query series S:

1. Load all `ai_summaries` embeddings of type `series` and `chapter` for S.
2. Compute the centroid vector: `mean(all S embeddings, axis=0)`.
3. For each other series T in the library (that has summary embeddings):
   a. Load T's centroid.
   b. Compute cosine similarity between S centroid and T centroid.
4. Return top-10 similar series, excluding S itself.

**Reading history boost (optional):**
Series the user is currently reading (`reading_status = 'reading'`) have their
similarity boosted by 10% in ranking, on the theory that completed-series
recommendations are more useful in the same style as current reads.

### Performance considerations

- With 1,000 series in the library: 1,000 centroid comparisons = < 10 ms in NumPy.
- With 100,000 series: use FAISS with a flat index (~5 ms query time).

### Failure handling

- Series has no embeddings: skip it in the candidate list. Return fewer than 10
  recommendations rather than erroring.

### GPU usage

**None.** Pure NumPy on CPU.

---

## 16. Stage 15 — Caching

Not a pipeline stage; a set of caching policies applied across the system.

### Image cache (browser + FastAPI)

| Resource | `Cache-Control` | Strategy |
|----------|-----------------|---------|
| Page images | `max-age=604800, immutable` | Files never change once indexed |
| Cover thumbnails | `max-age=86400` | Regenerated rarely |
| Generated images | `max-age=604800, immutable` | Content-addressed by hash |

FastAPI serves images with `FileResponse`, which sets `ETag` (file mtime hash)
and `Last-Modified` automatically. The frontend does not need to handle this.

### Application-level cache

| Data | TTL | Invalidation |
|------|-----|-------------|
| Series list (paginated) | Invalidated on scan complete | Event from WebSocket |
| Series detail | Invalidated on PATCH | TanStack Query `invalidateQueries` |
| Chapter list | Invalidated on scan complete | Event from WebSocket |
| Recommendation scores | 1 hour | Manual on new embedding complete |
| Vector search results | Not cached | FTS + cosine is fast enough |

TanStack Query handles all frontend caching. The backend is stateless for
read endpoints — no backend response cache needed.

### What is NOT cached

- OCR text: stored in DB, fetched on demand
- Chat messages: fetched from DB, no additional cache
- Search results: never cached (result set changes as OCR progresses)

---

## 17. Stage 16 — Background Workers

### Architecture

**Phase 2–4:** Python `threading.Thread` + a SQLite-backed task queue (`background_tasks`
table). Simple, no external dependencies.

**Phase 5+:** Migrate to ARQ (async task queue backed by Redis) for distributed
workers and better visibility.

### Worker types and concurrency

| Worker | Bound by | Max concurrency | Notes |
|--------|----------|-----------------|-------|
| Scanner | I/O (disk) | 1 per library root | Parallel scans of different roots |
| Thumbnailer | CPU | 4 threads | ThreadPoolExecutor |
| OCR | GPU | 1 | Serialized through Ollama |
| Embedder | GPU | 1 | Serialized through Ollama |
| Summarizer | GPU | 1 | Serialized through Ollama |
| Knowledge extractor | GPU | 1 | Serialized through Ollama |
| Download | Network | 3 | Phase 6; separate from AI workers |

### Task lifecycle

```
pending → running → completed
                  → failed (retry_count < max_retries → back to pending)
                  → cancelled
```

`background_tasks.progress_pct` is updated every 5 seconds during long tasks.
`background_tasks.progress_detail` contains a human-readable status string
(e.g., "Page 6,063 of 12,853").

### Priority queue

Workers poll the `background_tasks` table:

```sql
SELECT * FROM background_tasks
WHERE status = 'pending'
  AND (scheduled_at IS NULL OR scheduled_at <= CURRENT_TIMESTAMP)
ORDER BY priority DESC, created_at ASC
LIMIT 1;
```

Higher `priority` integer value = runs first.

### Startup behavior

On backend startup: any task in `status = 'running'` is reset to `status = 'pending'`
with `retry_count += 1`. This handles crash-recovery correctly.

### GPU serialization

All Ollama calls go through a single asyncio lock:

```python
ollama_lock = asyncio.Lock()

async def ollama_call(payload):
    async with ollama_lock:
        return await httpx.post("http://localhost:11434/api/...", json=payload)
```

This ensures no two Ollama requests run simultaneously, preventing VRAM OOM errors.

### Future scalability

- ARQ + Redis: workers become separate processes, enabling true GPU parallelism
  if the user upgrades to multiple GPUs.
- Task priorities become Redis sorted set scores.
- Worker health is monitored via heartbeat keys with TTL.

---

## 18. Stage 17 — Re-indexing

### Purpose

Regenerate AI output when the user changes model configuration, fixes errors, or
when a new model significantly outperforms the old one.

### Triggers

- User changes `ai.ocr_model` in settings → all OCR output is stale
- User changes `ai.embed_model` → all embeddings are stale
- User changes `ai.summary_model` or `ai.summary_prompt_version` → summaries stale
- User selects "Re-analyze series" from the UI
- Automatic re-index on version upgrade (when `prompt_version` field changes)

### Safety invariants

**User-edited rows are never deleted or overwritten.** Before any re-index operation:

```sql
-- Only delete AI-generated rows that the user has not manually edited
DELETE FROM ai_summaries
WHERE series_id = ? AND is_ai_generated = 1 AND is_user_edited = 0;
```

Character edits, manual timeline events, and manual knowledge entries are all
preserved across re-index operations.

### OCR re-index

1. For each `pages` row where the associated `ocr_pages.model != new_model`:
   a. Delete the `ocr_pages` row (triggers FTS5 delete trigger automatically).
   b. Delete `embedding_chunks` + `embeddings` derived from this page.
   c. Re-queue the page for OCR.
2. After OCR completes: re-run embedding and summary stages.

### Embedding re-index

1. Delete all `embeddings` rows where `model != new_model`.
   Keep `embedding_chunks` rows (text is model-independent).
2. Re-run Stage 9 for all existing chunks.

This is the cheapest re-index: OCR text and summaries are preserved; only
the vector representations need regeneration.

### Summary re-index

1. Delete `ai_summaries` where `is_user_edited = 0` and `model != new_model`.
2. Re-run Stage 11.

### Full knowledge re-index

1. Delete all `characters`, `character_relationships`, `timeline_events`,
   `world_locations`, `world_factions`, `world_lore` where `is_user_edited = 0`.
2. Re-run Stages 5–8.

### Performance

Re-index is treated as a lower-priority background task. It does not interrupt
normal reading or other active tasks.

---

## 19. Stage 18 — Incremental Updates

### Purpose

Keep the database in sync with the user's file system without a full rescan.
Responds to new chapters, modified archives, and deleted files.

### Triggers

| Event | Source | Action |
|-------|--------|--------|
| New folder/file in library root | File system watcher | Partial scan of that path |
| Periodic scan interval | Scheduler | Full rescan of library root |
| User clicks "Scan Now" | UI button | `POST /library/roots/{id}/scan` |

### File system watcher

Phase 3+: use `watchdog` (cross-platform Python library) to watch library roots.
One `Observer` thread per library root. Events:
- `FileCreatedEvent` / `DirCreatedEvent` → queue scan of parent directory
- `FileModifiedEvent` → re-hash; if changed, invalidate derived data
- `FileDeletedEvent` / `DirDeletedEvent` → soft-delete series/chapter

Debounce events with a 5-second window (a batch of new files from a file copy
should produce one scan task, not one per file).

### New chapter handling

1. Scanner detects new chapter directory or CBZ.
2. Insert `chapters` and `pages` rows.
3. Queue: thumbnail generation → OCR (if auto-OCR enabled) → embed → summarize.
4. Update `series.total_chapters`, `series.total_pages` denormalized counts.
5. Broadcast `series_updated` event via WebSocket notifications.

### Modified file handling

1. Scanner computes SHA-256 of the modified file.
2. Compare to `chapters.file_hash`. If unchanged: no-op.
3. If changed: delete all derived data for this chapter
   (`ocr_pages`, `embedding_chunks`, `embeddings`, `ai_summaries` for this chapter)
   where `is_user_edited = 0`.
4. Re-queue OCR → embed → summarize for this chapter.

### Deleted file handling

1. File system watcher detects deletion.
2. Mark `chapters.folder_path` (or `archive_path`) as null; set soft-delete sentinel
   or leave chapter in DB with `scanned_at` unupdated.
3. If the entire series directory is deleted: set `series.deleted_at = now`.
4. Reading progress is **preserved** even when series is soft-deleted. If the user's
   files return, the progress resumes.
5. `reading_progress.current_chapter_id` uses `ON DELETE SET NULL`, so progress
   survives chapter deletion.

### Incremental scan performance

A single new chapter (72 pages):
- Scan + insert: < 1 second
- Thumbnail: < 5 seconds
- OCR (72 pages × 2 sec): ~2.5 minutes
- Embed: ~30 seconds
- Summary: ~20 seconds
- Total: < 5 minutes to full AI indexing

This is the steady-state experience for a user adding a new weekly chapter release.

---

## 20. Model Configuration Reference

All models are configurable in `config/settings.json`. These are the defaults.

| Setting key | Default | Used in |
|-------------|---------|---------|
| `ai.ocr_model` | `minicpm-v:8b` | Stage 3 (OCR) |
| `ai.embed_model` | `nomic-embed-text` | Stage 9 (Embeddings) |
| `ai.default_writer` | `llama3.3:70b` | Stages 4, 11 (Metadata, Summaries) |
| `ai.default_reasoner` | `qwen3:30b` | Stages 5, 6, 7, 8, 13 (Knowledge, Chat) |
| `ai.embed_dimensions` | `768` | Stored in `embeddings.dimensions` |
| `ai.embed_batch_size` | `32` | Stage 9 batch call size |
| `ai.ocr_timeout_seconds` | `30` | Stage 3 per-page timeout |
| `ai.summary_prompt_version` | `1` | Stored in `ai_summaries.prompt_version` |

Changing `ai.ocr_model` or `ai.embed_model` triggers a re-index prompt in the UI
(the user is asked whether to re-process; it is not automatic).

---

## 21. End-to-End Processing Flow

For a newly imported series of 100 chapters (7,200 pages):

```
Scan                     →  5 min   (I/O bound, runs first)
Thumbnail generation     →  10 min  (CPU bound, parallel with OCR)
OCR (7,200 pages)        →  4 hrs   (GPU bound, gating step for AI)
Embedding (7,200 chunks) →  2 hrs   (GPU bound, runs after OCR)
Summary (100 chapters)   →  30 min  (GPU bound, runs after OCR)
Knowledge extraction     →  45 min  (GPU bound, runs after summaries)
Timeline generation      →  15 min  (GPU bound, runs after summaries)
World extraction         →  10 min  (GPU bound, runs after summaries)
─────────────────────────────────────────────────────────────────────
Total (sequential)       ~  8 hrs   (overnight background processing)
```

**The user can read from minute 1.** The reader serves page images directly from disk.
AI features (search, chat, knowledge) unlock progressively as stages complete.
The Library UI shows per-series `ai_status` progress bars so the user knows what's ready.

---

## 22. Pipeline Review Notes

### Review 1 — data flow correctness

- Every stage consumes only its required input; no stage skips ahead.
- `series_ai_status` is updated atomically per-stage, not per-item, to avoid
  database contention from high-frequency updates during OCR.
- FTS5 triggers keep the search index always in sync without extra code in the service layer.
- `is_user_edited = 1` check is enforced before every delete in all re-index operations.

### Review 2 — failure isolation

- No stage is a single point of failure for the library. A crash in OCR does not
  prevent the user from reading, scanning new chapters, or using FTS search.
- Per-item retry is independent. One corrupt page does not block 7,199 others.
- Ollama restart is handled by the 60-second retry loop in OCR worker; the queue
  is not drained.
- Startup recovery resets `running` tasks to `pending` with `retry_count += 1`,
  preventing tasks from being silently lost after a process crash.

### Review 3 — scale correctness

- BIGINT primary keys on `ocr_pages`, `embedding_chunks`, `embeddings`,
  `character_appearances` correctly handle > 2B rows without overflow.
- SQLite is the right choice through ~500K embeddings. The PostgreSQL migration
  is a connection-string change + one DDL statement (`ALTER COLUMN vector TYPE VECTOR`).
- The FTS5 `external content` mode avoids text duplication in the search index;
  the trigger-based sync adds zero maintenance overhead.
- Centroid-based recommendations scale to 100K series with NumPy alone.
  FAISS is the scale path, not a rewrite.
- Chunk/vector separation in the schema (`embedding_chunks` vs `embeddings`)
  means re-embedding with a new model never destroys the source text.
