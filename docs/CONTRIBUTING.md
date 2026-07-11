# ManhwaManiacs — Contribution Guide

This document establishes how contributions are made to ManhwaManiacs — by humans and AI
agents alike. Read it before writing any code.

Cross-references: [ARCHITECTURE_REVIEW_2026-07-11.md](ARCHITECTURE_REVIEW_2026-07-11.md) ·
[ROADMAP.md](ROADMAP.md)

---

## 1. Before You Start

Read these documents in this order:

1. [ARCHITECTURE_REVIEW_2026-07-11.md](ARCHITECTURE_REVIEW_2026-07-11.md) — the real
   current architecture, subsystem-by-subsystem state, known debt, and the priority
   roadmap (§9).
2. [ROADMAP.md](ROADMAP.md) — what the product is today and which phase you're working in.

Do not write code until you understand the context for your change. Read the files
you will modify before modifying them.

---

## 2. Repository Structure

```
aistudio/
├─ frontend/        Next.js 16 application (TypeScript, Tailwind v4)
├─ backend/         FastAPI application (Python 3.11+)
├─ config/
│  └─ settings.json Runtime configuration for the backend
├─ docs/            All project documentation
├─ memory/          Creation studio data (characters, world, etc.)
├─ projects/        User-created manhwa projects
└─ covers/          Generated thumbnails (runtime, not committed)
```

See [ARCHITECTURE_REVIEW_2026-07-11.md § 5](ARCHITECTURE_REVIEW_2026-07-11.md#5-folder-organization)
for the current folder organization of `frontend/src/` and `backend/`.

---

## 3. Development Setup

### 3.1 Backend

Requirements: Python 3.11+, Ollama (optional for non-AI features).

```powershell
# From the backend/ directory
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

→ API available at `http://127.0.0.1:8000`
→ Interactive API docs at `http://127.0.0.1:8000/docs`

### 3.2 Frontend

Requirements: Node.js 20+.

```powershell
# From the frontend/ directory
npm install
npm run dev
```

→ App available at `http://localhost:3000`

### 3.3 Optional: configure API URL

Create `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Omitting this file defaults to `http://127.0.0.1:8000`.

### 3.4 Windows-specific notes

- Run commands individually. Never use `&&` or `||` between commands.
- Use PowerShell, not Command Prompt.
- `venv\Scripts\activate` (backslash) on Windows; `venv/bin/activate` on Linux/macOS.
- See [archive/PROJECT_RULES.md § 13](archive/PROJECT_RULES.md#13-windows-compatibility-rules)
  (archived) for the full list of Windows compatibility requirements.

---

## 4. Coding Standards

### 4.1 TypeScript (frontend)

- Strict mode is always on. `strict: true` in `tsconfig.json` is not negotiable.
- No `any`. Use `unknown` + narrowing, or the correct type from `types/`.
- No `as Type` casts without a comment explaining why.
- All API response types live in `types/` and exactly match backend Pydantic models.
- Named exports only for shared components. No anonymous default exports.
- `'use client'` only on the component that needs it — push it as deep as possible.

```typescript
// Good: typed, no any, minimal client boundary
'use client'
import { useState } from 'react'
import type { Series } from '@/features/library/types'

interface Props {
  series: Series
  onSelect: (id: number) => void
}

export function SeriesCard({ series, onSelect }: Props) { ... }
```

```typescript
// Bad: any type, loose export, unnecessary client boundary on the page
export default function LibraryPage() {
  const [data, setData] = useState<any[]>([])
  ...
}
```

### 4.2 Python (backend)

- Python 3.11+. Use `from __future__ import annotations` in all files.
- Type annotations on all function signatures — parameters and return types.
- Pydantic models for all request and response bodies. No raw `dict` in or out.
- `snake_case` for functions, variables, and modules. `PascalCase` for classes.
- No business logic in route functions. Routes are thin (parse → call service → return).
- No SQLAlchemy queries outside the `database/` and `services/` layers.

```python
# Good: typed, thin route, service dependency injected
from typing import Annotated
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from services.library_service import LibraryService, get_library_service

router = APIRouter(prefix="/library", tags=["library"])

class SeriesListResponse(BaseModel):
    items: list[SeriesSummary]
    total: int

@router.get("/series", response_model=SeriesListResponse)
def list_series(
    service: Annotated[LibraryService, Depends(get_library_service)],
    page: int = 1,
    per_page: int = 40,
) -> SeriesListResponse:
    """Return a paginated list of all series in the library."""
    return service.list_series(page=page, per_page=per_page)
```

```python
# Bad: business logic in route, no types, raw dict return
@router.get("/library")
def get_library(db=Depends(get_db)):
    items = db.query(LibraryItem).all()
    return [{"id": i.id, "title": i.title} for i in items]
```

### 4.3 Styling

- No hardcoded colors. Use design token classes: `bg-surface`, `text-muted`,
  `border-border`, `text-primary`, etc.
- The `cn()` function from `@/lib/cn` is the only way to merge conditional classes.
- No `style` prop except for runtime-dynamic values that Tailwind cannot express.
- No light-mode conditional classes. The app is dark-only.

```tsx
// Good: design tokens, cn() for merging
import { cn } from '@/lib/cn'

<div className={cn(
  "rounded-lg border border-border bg-surface p-4",
  isActive && "border-primary"
)}>
```

```tsx
// Bad: hardcoded colors, inline style
<div style={{ backgroundColor: '#141417' }} className="border border-gray-700">
```

### 4.4 Comments

Write no comments except when the *why* is non-obvious. The what is in the code.

```python
# Good: explains a non-obvious constraint
# SQLite requires foreign_keys PRAGMA per-connection, not per-session.
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, _):
    dbapi_connection.execute("PRAGMA foreign_keys=ON")
```

```python
# Bad: explains what the code already says
# Get all series from the database
series = db.query(Series).all()
```

---

## 5. Branch Naming

```
<type>/<short-description>
```

| Type | When to use |
|------|-------------|
| `feat/` | New feature work |
| `fix/` | Bug fix |
| `refactor/` | Code restructuring without behavior change |
| `docs/` | Documentation only |
| `test/` | Tests only |
| `chore/` | Build scripts, dependencies, config |

**Examples:**
```
feat/library-scanner
feat/webtoon-reader
fix/cover-generation-path
refactor/split-database-module
docs/add-api-examples
chore/upgrade-tanstack-query
```

Rules:
- Always lowercase.
- Use hyphens, not underscores or spaces.
- Keep it under 50 characters.
- Branch from `main`. Never branch from another feature branch.
- One logical change per branch. Do not combine a bug fix with a new feature.

---

## 6. Commit Message Conventions

Format: `<type>(<scope>): <summary>`

The summary is imperative, present tense, lowercase, no period at the end.

```
feat(library): add recursive folder scanner with CBZ support
fix(reader): correct page order for right-to-left manga mode
refactor(database): migrate to SQLAlchemy 2.x declarative style
docs(roadmap): mark phase 2a backend tasks as complete
chore(frontend): upgrade TanStack Query to v5.101
test(scanner): add fixtures for mixed format library import
```

**Type reference:**

| Type | Meaning |
|------|---------|
| `feat` | New user-facing feature |
| `fix` | Bug fix |
| `refactor` | Code restructuring, no behavior change |
| `perf` | Performance improvement |
| `test` | Adding or correcting tests |
| `docs` | Documentation only |
| `chore` | Tooling, dependencies, config |
| `style` | Formatting, no logic change |

**Scope examples:** `library`, `reader`, `ai`, `search`, `database`, `frontend`,
`backend`, `scanner`, `keyboard`, `api`, `docs`.

**Multi-line format for significant changes:**
```
feat(scanner): add background library scanning with WebSocket progress

Scans are now non-blocking. Progress is streamed to the frontend via
WebSocket at /ws/scan-progress. The scan status endpoint is retained
for clients that cannot use WebSockets.

Closes #42
```

**Rules:**
- First line: 72 characters maximum.
- If more context is needed, leave a blank line, then write prose.
- Reference related issues with `Closes #N` or `See #N`.
- Never commit with a message like "fix", "update", "wip", or "changes".

---

## 7. Pull Request Process

### 7.1 Before opening a PR

Complete the recurring-rules checklist in [ROADMAP.md](ROADMAP.md#recurring-rules-every-phase);
the fuller historical Definition of Done is archived at
[archive/PROJECT_RULES.md § 18](archive/PROJECT_RULES.md#18-definition-of-done).
If any item fails, the PR is not ready.

### 7.2 PR title and description

PR title follows the same format as commit messages: `type(scope): summary`.

Description template:

```markdown
## What this changes

[One paragraph. Explain the change and why it was made.]

## How to test it

[Step-by-step instructions for a reviewer to verify the change works.]

## Checklist

- [ ] `npm run build` passes
- [ ] `npx tsc --noEmit` passes
- [ ] `python -m pytest` passes (if backend changes)
- [ ] No hardcoded colors
- [ ] No business logic in routes
- [ ] ROADMAP.md updated (if phase task completed)
- [ ] No TODO comments in committed code
- [ ] Error envelope intact for all new endpoints
```

### 7.3 PR size

- **Small PR (preferred):** One logical change. One feature sub-task. One bug fix.
  Reviewable in under 30 minutes.
- **Medium PR (acceptable):** A complete feature module (e.g., the full library scanner
  backend). Clearly scoped, well-described.
- **Large PR (requires justification):** A complete phase (e.g., all of Phase 2 backend).
  Acceptable only when the work is deeply interconnected and cannot be split.

Do not combine unrelated changes in a single PR. A bug fix found during feature work
gets its own PR.

---

## 8. Code Review Checklist

For every file changed, the reviewer verifies:

### Architecture
- [ ] Business logic is in services, not routes.
- [ ] No SQLAlchemy in routes; no HTTP logic in services.
- [ ] New features have their code in `features/<name>/` not scattered in `app/` or `services/`.
- [ ] `'use client'` is on the smallest possible component.
- [ ] Server data uses TanStack Query; UI state uses Zustand.

### TypeScript / Python quality
- [ ] No `any` types.
- [ ] All function parameters and return types are annotated (Python).
- [ ] All API response types match their Pydantic models.
- [ ] Error cases are handled (not just the happy path).
- [ ] Input validation exists for all user-provided values.

### Design system
- [ ] No hardcoded colors — all design token classes.
- [ ] `cn()` used for conditional class merging, not string concatenation.
- [ ] Matches the dark theme (no light-theme classes like `bg-white`, `text-black`).

### Performance
- [ ] Lists of unbounded size use pagination or virtual scrolling.
- [ ] No N+1 database queries.
- [ ] No blocking operations in a request handler.

### Correctness
- [ ] Edge cases are covered: empty state, error state, loading state.
- [ ] Reading progress is saved correctly.
- [ ] File path validation prevents path traversal.
- [ ] Error envelope shape is correct for all new endpoints.

### Documentation
- [ ] FastAPI docstrings on new endpoints.
- [ ] `ROADMAP.md` updated if a phase/milestone task is completed.

---

## 9. Testing Checklist

Run these commands separately (never chain with `&&`):

```powershell
# TypeScript type checking
npx tsc --noEmit

# Production build (catches runtime errors that tsc misses)
npm run build

# Lint
npm run lint

# Backend tests (when they exist)
python -m pytest
```

All four must pass. Zero tolerance for failures.

### Continuous integration

`.forgejo/workflows/ci.yml` runs on every push to `master`/`develop`/`main` and
on every pull request. It has three jobs that mirror the checklist above:

- **backend** — `pip install -r requirements.txt` then `pytest`.
- **frontend** — `npm ci`, then `npm run typecheck`, `lint`, `test`, `build`.
- **mobile** — `flutter pub get`, `flutter analyze`, `flutter test`.

CI is the correctness gate that keeps the trunk releasable; it is independent of
the deploy pipelines (staging/production/preview). Get your change green locally
before opening a PR — CI should confirm, not discover.

### Writing tests

**Backend tests** go in `backend/tests/`. Use `pytest`. Use `tmp_path` for file
fixtures. Use a fresh in-memory SQLite database per test.

```python
# backend/tests/test_library_service.py
def test_scan_detects_series(tmp_path):
    # Arrange: create a known folder structure
    series_dir = tmp_path / "My Series"
    chapter_dir = series_dir / "Chapter 001"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "001.jpg").write_bytes(b"...")

    # Act
    service = LibraryService(db=in_memory_db())
    result = service.scan_library(str(tmp_path))

    # Assert
    assert result.series_count == 1
    assert result.chapter_count == 1
```

**Frontend tests** (when added, Phase 2+): test feature hooks and components in
isolation. Mock at the `services/http.ts` boundary — never make real HTTP calls in tests.

---

## 10. Documentation Checklist

When your change touches any of the following, update the corresponding document:

| Change | Update required |
|--------|----------------|
| Completed roadmap task | `ROADMAP.md` (mark complete, update dates) |
| Major architectural change | `ARCHITECTURE_REVIEW_2026-07-11.md` (or a dated follow-up review) |
| New API endpoint | FastAPI docstring (auto-generates OpenAPI spec) |
| New shortcut | `CONTRIBUTING.md` (keyboard reference, when added) |

Documentation is not optional. An undocumented change is an incomplete change.

---

## 11. How AI Agents Should Contribute

AI agents (Claude, GitHub Copilot, Cursor, etc.) follow the same standards as human
contributors, with additional requirements.

### 11.1 Read before writing

Before modifying any file, read it. Before creating any file in a module, read the
adjacent files to understand the existing patterns. Never write code that duplicates
what already exists without reading the existing implementation first.

### 11.2 Read the relevant docs

For any non-trivial change:
1. Read [ARCHITECTURE_REVIEW_2026-07-11.md](ARCHITECTURE_REVIEW_2026-07-11.md) for the
   subsystem map, dependency graph, and known debt for the layer being changed.
2. Read [ROADMAP.md](ROADMAP.md) to confirm which phase/milestone the change belongs to.

For frontend changes specifically:
- Read `frontend/node_modules/next/dist/docs/` for the relevant Next.js 16 API before
  writing routes, layouts, or using `params`/`searchParams`. Next.js 16 has breaking
  changes from earlier versions. The installed docs are authoritative.

### 11.3 Scope discipline

Do not write more than the task requires. A bug fix does not need surrounding cleanup.
A feature does not need a more general abstraction than the feature requires. Do not
add features, refactor, or extend scope without being asked.

### 11.4 Verification

Before reporting a task complete, run the verification commands. Report the actual
output. Do not claim success without evidence.

```powershell
# Frontend
npx tsc --noEmit
npm run build

# Backend
# (Import test — start the app and check endpoints)
python -c "import main; print('Import OK')"
python -m pytest  # when tests exist
```

### 11.5 Never fake implementations

If a dependency is missing (e.g., `Pillow` not installed), do not write code that
pretends it is installed. Either install the dependency (with justification) or
implement a path that handles its absence gracefully. Never return mock data from
a function that claims to do real work.

### 11.6 Error reporting

When something cannot be implemented as specified, say so clearly and explain why.
Do not silently implement a different, simpler version without flagging the deviation.

### 11.7 One source of truth

If a type is already defined in `types/`, use it. If a service already exists, use it.
If a utility already exists in `lib/`, use it. Never create a second definition of
something that already exists.

---

## 12. How Humans Should Review AI-Generated Code

AI agents write plausible-looking code that can silently violate architecture rules,
introduce subtle bugs, or silently downgrade to simpler implementations. Review it
with appropriate skepticism.

### 12.1 Verify the critical contracts

For every AI-generated file, manually check:

**Frontend:**
- Is server data going through TanStack Query? Check `features/<name>/hooks.ts`.
- Is UI state going through Zustand? Check `stores/`.
- Is `'use client'` on the right component (not on the page)?
- Are design tokens used? Search for `bg-gray`, `text-gray`, `#`, `rgb(` in the diff.
- Are there hardcoded hex values anywhere?

**Backend:**
- Are routes thin? Is there SQL or file I/O inside a route function?
- Is the error envelope correct? Every exception must produce `{code, message, details?}`.
- Are file paths validated before use?
- Is there any `print()` statement?

### 12.2 Verify imports

AI agents frequently import things that don't exist, use deprecated imports, or import
from the wrong location. Check every import in every changed file:
- Does the module exist?
- Is the export name correct?
- Is it using the right import path (`@/` for frontend, absolute for backend)?

### 12.3 Run the build

Do not trust "it should work." Run `npm run build` and `npx tsc --noEmit` yourself.
AI agents report success based on code they believe is correct — not on builds they
have run. The build is the ground truth.

### 12.4 Test the actual behavior

For backend changes: hit the endpoints with `curl` or the Swagger UI at `/docs`.
For frontend changes: open the browser and use the feature. Check the network tab for
correct API calls. Check the console for errors.

### 12.5 Check for silent regressions

AI-generated code frequently breaks previously working functionality while fixing
something else. After reviewing the changed files, also manually test any feature
that shares the same data model or component as the change.

### 12.6 Trust but verify scope

If an AI agent claims to have completed a task, verify against the acceptance criteria
in [ROADMAP.md](ROADMAP.md). "I have implemented X" must be verified by:
1. The feature visibly working in the browser (not just the code existing).
2. The build passing.
3. The type checker passing.
4. No regressions in adjacent features.

---

## 13. Questions and Decision Log

When a non-obvious decision is made during development — a tradeoff, a deviation from
the planned approach, a discovery that changes the design — document it.

If the decision is architectural: note it in a dated follow-up to
[ARCHITECTURE_REVIEW_2026-07-11.md](ARCHITECTURE_REVIEW_2026-07-11.md).

If the decision changes the phase plan: update [ROADMAP.md](ROADMAP.md).

Undocumented decisions become unexplained surprises for the next person (or AI agent)
who reads the code. The documentation is the institutional memory of this project.
