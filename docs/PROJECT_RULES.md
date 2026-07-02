# AIStudio — Project Rules

This is the permanent, authoritative rulebook for AIStudio. It governs every decision
made in this project — by humans and AI agents alike. When in doubt, consult this
document first.

Cross-references: [VISION.md](VISION.md) · [ARCHITECTURE.md](ARCHITECTURE.md) ·
[ROADMAP.md](ROADMAP.md) · [CONTRIBUTING.md](CONTRIBUTING.md)

---

## 1. Project Philosophy

AIStudio exists to give people complete control over their comic library and the AI
that understands it. Everything runs locally. The user's data never leaves their machine
unless they explicitly ask it to.

The three-sentence mission:
> Build the best self-hosted manhwa, manga, and manhua platform in the world.
> Make it work entirely on local hardware.
> Make it the last tool a reader or creator ever needs.

The standard for quality is commercial software, not a weekend project. Every screen,
every interaction, every API response should feel like it was built by a team that
cares about the product.

---

## 2. Long-term Vision

AIStudio will grow to surpass each of these tools in its domain, then unify them:

| Tool | What we surpass | How |
|------|----------------|-----|
| Kavita / Komga | Library management, reading | + AI metadata, creation, knowledge graph |
| Mihon / Tachiyomi | Mobile reading UX | + Local AI, no source dependency, desktop power |
| Calibre | Metadata management | + Built for images/comics, not books |
| Jellyfin | Media library philosophy | + AI understanding, not just indexing |
| Obsidian | Knowledge graph | + Connected to the actual content, not separate |
| ChatGPT / NotebookLM | AI Q&A, summarization | + Local, integrated with the library |

The full vision is documented in [VISION.md](VISION.md). This document governs the
*how* of getting there.

---

## 3. Core Principles

These are not guidelines. They are the foundations on which every decision rests.

### 3.1 Working code first

A feature that works imperfectly beats a perfect design that does not exist. Ship
something the user can touch, then improve it. Do not design indefinitely.

### 3.2 Local-first, always

The application must function completely offline. Network features — sync, downloads,
NAS access — are additive enhancements, never prerequisites. If a feature requires
internet to work at all, it is a Phase 6+ feature.

### 3.3 One product, not a patchwork

All features share the same data model, design language, and keyboard grammar. Library
data feeds the Reader. Reader progress feeds AI. AI metadata feeds Search. Search feeds
the Knowledge Graph. Breaking that chain breaks the product.

### 3.4 AI augments; it does not replace

The core reading and library experience must be fully functional without any AI model
loaded. AI enhances the experience on top of a working foundation. A user with no
Ollama installed should still be able to import, browse, and read.

### 3.5 Keyboard-first, mouse-friendly

Every primary action in the application has a keyboard shortcut or can be assigned one.
Keyboard shortcuts are not an afterthought — they are defined at the same time as the
feature. A feature without its primary shortcut is not done.

### 3.6 Performance is a feature

Slowness is a bug. The application must remain fast at 100,000+ chapters. If a design
would be slow at that scale, choose a different design. Virtual scroll, pagination,
indexed queries, background processing — use them from the start, not after things
break.

### 3.7 Reversible decisions where possible

Prefer designs that can be changed without data loss or breaking changes. The database
schema is versioned with Alembic. API contracts are documented. The storage format for
user content (original files) never changes because we never move them.

---

## 4. Non-Negotiable Rules

These rules have no exceptions. Violating them requires explicit architectural decision
documentation explaining why the violation was unavoidable.

1. **Never move or copy the user's original files.** The app indexes; it does not own.
2. **Never introduce a cloud dependency for core functionality.** AI, search, and reading work offline.
3. **Never place business logic in a route.** Routes parse HTTP; services do work.
4. **Never put server data (API responses) in Zustand.** Server state belongs to TanStack Query.
5. **Never put UI state (sidebar open, modal visible) in TanStack Query.** UI state belongs to Zustand.
6. **Never break the error envelope contract.** Every error response is `{code, message, details?}`.
7. **Never hard-code colors or spacing.** Only design tokens (`var(--color-*)`) or Tailwind token classes.
8. **Never claim a feature is complete without running the verification checklist.**
9. **Never leave `TODO` comments in committed code.** Either implement it or document it as a future phase item in ROADMAP.md.
10. **Never implement a placeholder that pretends to do real work.** A stub that returns empty data is preferable to a fake implementation that returns invented data.
11. **Never sacrifice correctness for speed of development.**
12. **Never add a dependency without documenting why in ARCHITECTURE.md.**

---

## 5. Architecture Rules

The architecture is documented in full in [ARCHITECTURE.md](ARCHITECTURE.md). The
rules below are the enforced invariants.

### 5.1 Layer boundaries

```
Frontend:  app/ routes → features/ → services/http → backend
Backend:   routes/ → services/ → database/
```

- Routes depend on services. Services depend on the database layer and external clients.
- Nothing in the frontend touches the database directly.
- Nothing in a route file contains SQL, ORM queries, or file I/O.
- Nothing in a service file contains HTTP response construction.

### 5.2 Feature encapsulation

Each feature pillar (library, reader, search, ai, knowledge, create) owns its code:
- `features/<name>/api.ts` — API calls for this feature
- `features/<name>/hooks.ts` — TanStack Query wrappers
- `features/<name>/types.ts` — domain types (matching backend Pydantic models)
- `features/<name>/components/` — UI components private to this feature

Code shared across two or more features moves to `components/ui/`, `lib/`, or `services/`.

### 5.3 State ownership

| Data type | Owner |
|-----------|-------|
| API responses, library data, reading progress | TanStack Query |
| Sidebar state, reader mode, active modal | Zustand |
| Form input, local component state | React `useState` |
| Computed derivations from the above | Derived in component or `useMemo` |

Never mix. Mixing causes stale UI, cache invalidation bugs, and silent data divergence.

### 5.4 Dependency injection

Backend services are singleton instances created via `@lru_cache` factory functions
and injected via FastAPI `Depends()`. Services are never instantiated inside routes.

### 5.5 Keyboard shortcuts

All shortcuts are registered through `useShortcut()` from `lib/keyboard/`. No
`addEventListener` calls on `window` outside the keyboard module. The registry is the
single source of truth for all keyboard behavior and powers the help overlay.

---

## 6. Frontend Rules

### 6.1 Component discipline

- **Server Components by default.** Every `page.tsx` is a Server Component unless it
  explicitly needs browser APIs, state, or event handlers.
- **Push `'use client'` deep.** Add it to the smallest component that needs it. Avoid
  marking a large tree as client-only when only a button inside it is interactive.
- **No anonymous default exports** for shared components. Named exports only.
- **One component per file.** Small helper sub-components can coexist if they are not
  exported and are fewer than 40 lines.

### 6.2 Styling

- Use design token classes (`bg-surface`, `text-muted`, `border-border`) — never raw
  hex values, `bg-gray-*`, or `text-zinc-*`.
- The `cn()` function from `lib/cn.ts` is the only way to merge conditional classes.
- No inline `style` attributes except for dynamic values that Tailwind cannot express
  (e.g., a runtime-computed `transform: translateY(${offset}px)`).
- Dark mode is not a toggle. The application is dark-only. There is no light mode.

### 6.3 TypeScript

- Strict mode is always on. `strict: true` in `tsconfig.json` is non-negotiable.
- No `any`. Use `unknown` and narrow it, or use the correct type.
- No `as Type` casts without a comment explaining why the type system cannot prove it.
- All API response types in `types/` must exactly match the corresponding Pydantic models.

### 6.4 Performance

- Never load all data up front if the list could exceed 100 items. Paginate or
  virtualize from the start.
- Images in the reader: eager-load the visible viewport; `loading="lazy"` for all
  others. Always include explicit `width`/`height` to prevent layout shift.
- No synchronous operations on the main thread that take more than 16ms.
- Memoize expensive computations with `useMemo`. Do not memoize cheap ones.

### 6.5 Accessibility

- All interactive elements are keyboard-reachable.
- All images have meaningful `alt` text or `alt=""` if decorative.
- Color alone is never the sole means of conveying information.
- Focus indicators are visible and match the design system.

---

## 7. Backend Rules

### 7.1 Routes are thin

A route function does exactly three things: validate input (via Pydantic), call a
service method, return the result. If a route function exceeds 20 lines, the logic
belongs in the service layer.

### 7.2 Services are stateless

Services hold no per-request state. They receive arguments, do work, return results.
State lives in the database or in the background worker's task queue.

### 7.3 Error handling

All errors propagate as `AppError` instances or are caught by the registered exception
handlers in `core/errors.py`. Never return an error as a 200 OK response. Never let
an unhandled exception reach the client without going through the error handler.

### 7.4 File paths

Every file path provided by the user is validated to be:
1. An absolute path.
2. Within a registered library root path (`Path.is_relative_to()`).
3. Pointing to a file that exists.

Failure to validate file paths is a path traversal vulnerability.

### 7.5 Background tasks

Long-running operations (scans, OCR, thumbnail generation, embedding) are never
synchronous within a request/response cycle. They are dispatched to background workers.
The API immediately returns a task ID or status URL; the client polls or subscribes via
WebSocket.

### 7.6 Configuration

- All configuration reads go through `get_settings()` from `core/config.py`.
- No `os.environ.get()` calls scattered through service files.
- `config/settings.json` is the single configuration surface for operators.

### 7.7 SQL hygiene

- No raw SQL strings. Use SQLAlchemy ORM or Core expressions exclusively.
- No SQLite-specific syntax. Write queries that will run on PostgreSQL without changes.
- Every foreign key has a corresponding index.
- Every query that filters by a user-provided value uses parameterized expressions (ORM
  handles this automatically; raw SQL does not).

---

## 8. Database Rules

### 8.1 Normalization

Data is stored once and referenced by foreign key. If the same string appears in two
rows in two tables and could change, it is a normalization violation. Extract it.

### 8.2 Schema evolution

- All schema changes go through Alembic migrations. No `CREATE TABLE` in application code.
- Migrations are additive where possible (add columns, add tables).
- Breaking changes (drop column, rename column) require a migration plan documented
  in the migration file header.
- No migration removes data without an explicit data-export step beforehand.

### 8.3 Foreign keys

SQLite requires `PRAGMA foreign_keys = ON` to enforce foreign key constraints. This
pragma is set in the session factory for every connection. It is never disabled.

### 8.4 PostgreSQL compatibility

The SQLite deployment is the development default. The production target is PostgreSQL.
This means:
- No `AUTOINCREMENT` keyword (use `INTEGER PRIMARY KEY` in SQLite; SQLAlchemy handles it).
- No SQLite-only functions (`strftime` in queries, etc.).
- No blob storage for large binary data — use file paths and serve files directly.
- Embeddings stored as `BLOB` now; will become `pgvector` column type on migration.

### 8.5 Sensitive data

- No passwords stored without bcrypt or argon2 hashing (when multi-user arrives).
- No API keys or tokens in the database. They belong in `config/settings.json`.
  `config/settings.json` may be committed with safe default values (URLs, model names).
  If it ever contains user secrets (API keys, tokens), add it to `.gitignore` and
  provide `config/settings.example.json` as the committed template instead.
- Reading history is personal data — design with deletion in mind from day one.

---

## 9. AI Rules

### 9.1 Local only

All AI features use Ollama and local models. No API calls to OpenAI, Anthropic,
Google, or any other cloud AI provider for core features. Cloud AI may only be used if:
1. The user has explicitly opted in.
2. The feature works (degraded or absent) without it.
3. No user content is sent to the cloud without confirmation.

### 9.2 Model configuration

Models are configured per task in `config/settings.json`. Default models are:
- `default_chat` — general Q&A, character interaction.
- `default_writer` — summaries, descriptions, prose generation.
- `default_reasoner` — complex inference, timeline analysis.
- `default_vision` — OCR, panel analysis.
- `default_embedder` — text embeddings for semantic search.

Each model can be overridden per request by the user.

### 9.3 Graceful degradation

Every feature that uses AI must work (possibly with reduced functionality) when Ollama
is not running or a model is not loaded. The UI must show a clear, helpful message
when AI is unavailable — not an error page.

### 9.4 AI output is user-correctable

AI-generated metadata (summaries, character names, tags, descriptions) is always
editable. The AI output is a starting point, not ground truth. The user's manual
corrections always take precedence over re-generated AI content.

### 9.5 Transparency

When displaying AI-generated content, always indicate that it was AI-generated and
which model produced it. The user must be able to distinguish AI output from manually
curated data.

### 9.6 Rate and resource management

OCR, embedding, and summary generation are resource-intensive. They run as queued
background tasks, never in parallel beyond what the hardware can sustain. The user
controls the queue depth and can pause/cancel processing at any time.

---

## 10. Performance Rules

### 10.1 Scale targets

The system must remain responsive at:
- 10,000+ series in the library
- 100,000+ chapters
- Millions of individual page images
- Concurrent background AI processing

### 10.2 Query performance

- Every query that filters by `series_id`, `chapter_id`, or `folder_path` has a
  database index on those columns.
- No N+1 queries. If displaying a list of series with chapter counts, that is one
  query with a join — not one query per series.
- Paginate any list that could exceed 100 items before it reaches the client.

### 10.3 Image serving

- Images are served via `FileResponse` with `Cache-Control: max-age=86400`.
- Thumbnails/covers are pre-generated; never resize on request.
- The reader prefetches the next chapter's images before the user reaches the last page.
- Images in the library grid use lazy loading; images in the reader use eager loading
  for the visible viewport with lazy for the rest.

### 10.4 UI performance

- Virtual scrolling is used wherever a list could exceed 50–100 items: series grid,
  chapter list, search results, character appearances.
- `useMemo` and `useCallback` are used for expensive derivations, not premature.
- No `useEffect` that triggers on every render. Dependency arrays must be exact.

### 10.5 Background processing

- Scanning, OCR, thumbnail generation, and embedding are always background operations.
- The application is fully usable while background processing is occurring.
- Background progress is communicated to the UI via polling or WebSocket — not by
  blocking the response.

---

## 11. Security Rules

### 11.1 Path validation

Every file path received from user input is validated against registered library root
paths using `Path.is_relative_to()`. This is enforced in the service layer, not the
route layer, so it cannot be bypassed.

### 11.2 Network binding

The backend binds to `127.0.0.1` by default — accessible only from the local machine.
CORS allows only the configured frontend origin. LAN/WAN access is an opt-in network
configuration, not a default.

### 11.3 Input validation

All user input is validated by Pydantic models before reaching service code. Unknown
fields are rejected. String fields have `min_length` and `max_length` constraints.
Numeric fields have `ge`/`le` bounds where the domain allows it.

### 11.4 Authentication

- Single-user mode: no authentication required (local-only access).
- Multi-user mode (Phase 6): JWT access tokens + secure refresh tokens. Bcrypt or
  Argon2 for password hashing. Session revocation list in the database.

### 11.5 SQL injection

SQLAlchemy ORM and Core expressions are used exclusively. Parameterized queries are
guaranteed by the ORM. No raw SQL string concatenation.

### 11.6 Model injection

AI model names provided by users are validated against the list of models actually
available in Ollama before being used in requests. Arbitrary model names are rejected.

---

## 12. Offline-First Rules

### 12.1 Core functionality requires no network

Import, scan, browse, and read — these four operations work with no network connection.
They have worked offline since the first day they were implemented.

### 12.2 Network features degrade gracefully

Features that optionally use network (cover fetching, metadata lookup, download manager)
show clear fallback states when offline. They never break the core experience.

### 12.3 No hard network timeouts in core paths

The reader never hangs waiting for a network call. If a resource is not available
locally, the reader shows an error for that resource and continues with others.

### 12.4 Progress is always saved locally

Reading progress, bookmarks, and user-edited metadata are written to the local SQLite
database immediately. They do not require a network sync to persist.

---

## 13. Windows Compatibility Rules

The primary development and deployment target is **Windows**. These rules apply to all
code, scripts, and documentation.

### 13.1 Path separators

Use `pathlib.Path` in all Python code. Never concatenate path strings with `/` or `\\`.
`Path` handles separators correctly on all platforms.

### 13.2 Command execution

Never use shell command chaining (`&&`, `||`, `;`) in documentation or scripts.
Run commands individually. In PowerShell, use separate lines or the PowerShell pipeline.

```powershell
# Correct
npm run build
npm run lint

# Incorrect
npm run build && npm run lint
```

### 13.3 Shell scripts

Use PowerShell (`.ps1`) for automation scripts, not Bash. If a script must also run
on Linux/macOS, provide both versions. Never assume `bash`, `sh`, `open`, or `xdg-open`.

### 13.4 File system

- Windows paths may contain spaces; always wrap paths in quotes when passing to CLI tools.
- File names in archives (CBZ, ZIP) may contain characters invalid on Windows — sanitize
  when extracting or when creating file-system paths.
- SQLite database files use the `.db` extension, stored in the `backend/` directory.

### 13.5 Process management

- Use `uvicorn` on Windows (not Gunicorn — Unix-only).
- Background workers use `threading` or `asyncio`, not `multiprocessing.fork`.
- The `watchdog` library uses the Windows native `ReadDirectoryChangesW` backend.

---

## 14. Cross-Platform Strategy

Windows is primary. Linux and macOS follow. Mobile and NAS are Phase 6.

| Platform | Priority | Notes |
|----------|----------|-------|
| Windows 10/11 | Primary | All development and testing |
| Linux (Ubuntu/Debian) | Secondary | NAS deployment target |
| macOS | Secondary | Developer machines |
| Android (PWA) | Phase 6 | Mobile reading via responsive web |
| iOS (PWA) | Phase 6 | Same |
| Synology NAS | Phase 6 | Docker container |

**Rules for cross-platform readiness:**
- Use `pathlib.Path` everywhere (not string paths).
- Use `platform.system()` to detect the OS when behavior must differ.
- Avoid Windows-specific APIs in core code; isolate platform differences in `utils/`.
- The Docker image targets Linux and must produce an identical feature set to Windows.
- The frontend has no platform-specific code — it runs in any modern browser.

---

## 15. Scalability Rules

### 15.1 Design for 100x current scale

Every design decision is evaluated at 100,000 chapters, not at 100. If the design
would break or become unbearably slow at that scale, it is the wrong design today.

### 15.2 Horizontal data patterns

- Lists are always paginated. Pagination parameters (`page`, `per_page`) are consistent
  across all list endpoints.
- Sorting and filtering happen in the database, not in Python application code.
- Search is index-backed (FTS5 for text, vector index for semantic). Never iterate
  over all rows to find matches.

### 15.3 Storage growth

- Covers are stored at fixed maximum dimensions (300×450px) regardless of original size.
- Embeddings are stored as compact byte blobs; a single 768-dimension float32 embedding
  is 3KB. 10 million of them is 30GB — plan storage accordingly.
- OCR text for a typical chapter is 5–20KB. 100,000 chapters is 500MB–2GB — acceptable.

### 15.4 PostgreSQL readiness

Every SQLAlchemy query written today runs without modification on PostgreSQL. This is
enforced by using only SQLAlchemy ORM/Core expressions. The PostgreSQL migration is a
configuration change, not a code rewrite.

---

## 16. Testing Requirements

### 16.1 What must be tested

- All service layer logic. Services are the heart of the application; they must have
  unit tests.
- All API endpoints. Use FastAPI's `TestClient` to verify request/response contracts.
- All database operations. Use a test SQLite database, never the production database.
- All file scanning logic. Use a temporary directory with known fixture files.

### 16.2 What does not need to be tested

- Next.js framework behavior. Trust the framework.
- Third-party library internals (SQLAlchemy, Pydantic, Ollama client).
- Purely presentational components that have no logic.

### 16.3 Test isolation

- Backend tests use a fresh SQLite database for every test (in-memory or temp file).
- Backend tests never call real Ollama. Mock the `OllamaService` at the service boundary.
- Backend tests never use real user files. Use `tmp_path` fixtures with known test data.
- Frontend component tests never make real HTTP calls. Mock at the `services/http.ts` boundary.

### 16.4 Test commands

Run separately — never chain with `&&`:
```
# Backend
python -m pytest

# Frontend (when test suite exists)
npm run test
npm run typecheck
npm run build
```

All four must pass before a pull request is merged.

---

## 17. Documentation Requirements

### 17.1 When documentation is required

- **Any new public API endpoint:** document in the route file's docstring (FastAPI generates the OpenAPI spec from this) and in ROADMAP.md if it was planned.
- **Any new feature module:** add its intended structure to STRUCTURE.md.
- **Any architectural decision:** add a row to the technology table in ARCHITECTURE.md.
- **Any new phase completion:** update ROADMAP.md to mark it complete and STRUCTURE.md to reflect new files.
- **Any non-negotiable rule violated** (even intentionally): document why in this file.

### 17.2 Code comments

Write no comments except when the *why* is non-obvious: a workaround for a known bug,
a constraint from an external system, or an invariant that would surprise a reader.

Never comment *what* code does — the code itself should be clear enough. Never leave
TODO comments in committed code. Never leave debug comments (`print`, `console.log`).

### 17.3 The documentation hierarchy

```
VISION.md       → Why this exists; what it becomes
PRODUCT.md      → Who it's for; what they need; competitive landscape
PROJECT_RULES.md → How we build it; the permanent rulebook
ARCHITECTURE.md → The technical decisions and their rationale
ROADMAP.md      → When we build what; acceptance criteria per phase
STRUCTURE.md    → Where code lives; full intended layout
CONTRIBUTING.md → How to contribute; branch/commit/review standards
```

Each document has a distinct purpose. Do not duplicate information between them.
Cross-reference with relative links.

---

## 18. Definition of Done

A feature, fix, or phase is **Done** when every item in this checklist passes.
"Done" is binary. Partial completion is "In Progress."

### Build verification
- [ ] `npm run build` passes with zero errors or warnings.
- [ ] `npx tsc --noEmit` passes with zero errors.
- [ ] `python -m pytest` passes (when tests exist for the changed area).

### Code quality
- [ ] No `any` types introduced without documented justification.
- [ ] No hardcoded colors or pixel values — design tokens only.
- [ ] No business logic in routes.
- [ ] No server data in Zustand; no UI state in TanStack Query.
- [ ] No imports of the database layer in frontend code.
- [ ] All new components use `'use client'` only where necessary.

### Feature correctness
- [ ] The feature works end-to-end: frontend → API → service → database → response → UI.
- [ ] Error states are handled: API down, empty data, validation failure.
- [ ] Loading states are visible during async operations.
- [ ] The primary keyboard shortcut for the feature is registered and documented.

### Documentation
- [ ] STRUCTURE.md updated for any new files or directories.
- [ ] ROADMAP.md updated if a phase step is complete.
- [ ] ARCHITECTURE.md updated if a new dependency or design decision was made.
- [ ] All new API endpoints have FastAPI docstrings (generates OpenAPI spec).

### No regressions
- [ ] Previously working features still work.
- [ ] The error envelope contract is intact for all new and existing endpoints.
- [ ] Design tokens are consistent across new and existing components.

---

## 19. Things That Must Never Happen

These are absolute prohibitions. There are no exceptions.

### Code

- **Never duplicate business logic** between a route and a service, or between two service files.
- **Never introduce a cloud AI API** (OpenAI, Anthropic, Google Gemini, etc.) as a required dependency for any core feature.
- **Never copy or move the user's original library files.** The application is an index, not a file manager.
- **Never write raw SQL strings** — use SQLAlchemy ORM or Core expressions.
- **Never write a fake or stub implementation** that pretends to do real work. If something cannot be implemented, return a clear error or make it a documented placeholder.
- **Never ship `console.log` statements** in committed code.
- **Never ship Python `print()` statements** in committed code (use the logging module).
- **Never disable TypeScript strict mode** or suppress errors with `@ts-ignore` without documented justification.
- **Never access `os.environ` directly** in service or route code — use `get_settings()`.
- **Never skip input validation** for any value that originates from outside the process (HTTP request, file system, config file).

### Architecture

- **Never place a SQLAlchemy query inside a route function.**
- **Never render a page that requires `useState` or `useEffect` without `'use client'`.**
- **Never store API response data in Zustand.**
- **Never store UI state (open/closed, active tab) in TanStack Query.**
- **Never register a keyboard listener with `addEventListener` outside the keyboard module.**
- **Never break the error envelope** `{code, message, details?}` — adding fields is OK; removing or renaming `code` or `message` is not.

### Development process

- **Never claim completion without running the Definition of Done checklist.**
- **Never merge code that fails `npm run build` or `npx tsc --noEmit`.**
- **Never leave a `TODO` comment in committed code.** Decide: implement it now or add it to ROADMAP.md.
- **Never start Phase N+1 before Phase N is verified complete** per the ROADMAP.md acceptance criteria.
- **Never add a package to `package.json` or `requirements.txt` without documenting the reason** in ARCHITECTURE.md or the relevant service file.
- **Never break backwards compatibility** of an existing API endpoint without a deprecation notice and a migration path.
- **Never sacrifice application performance** for a visual effect. Animations must be pure CSS transforms and opacity — never `top/left` position changes.
