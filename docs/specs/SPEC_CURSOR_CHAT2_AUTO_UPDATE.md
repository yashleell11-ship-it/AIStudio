# Implementation Spec: Automatic Update System
**Agent:** Cursor Chat 2  
**Architect sign-off:** Chief Software Architect  
**Date:** 2026-07-01  
**Status:** Ready to implement

---

## 1. Goals

Build a complete, production-ready automatic update system for AIStudio. The system must detect when a new version is available, notify the user non-intrusively, and (in Phase 1) direct the user to download the update manually. A later sprint will add silent background install.

Phase 1 (this sprint): detect → notify → link to release.  
Phase 2 (future sprint, not in scope): download → verify → apply → restart.

---

## 2. Scope

### In scope
- Backend: new `routes/update.py` with version check endpoints
- Backend: extend `core/config.py` with update-related settings (non-breaking additions only)
- Frontend: `features/update/` module (version check hook, notification banner component)
- Frontend: integrate banner into `app-shell.tsx` (one-line addition)
- Background polling: check for updates on startup and every 4 hours while the app is open
- Update manifest format: versioned JSON schema

### Out of scope
- Actually downloading or applying the update binary
- Windows installer (.msi/.exe) packaging
- Tauri/Electron integration
- Auto-restart
- Update history log (deferred to Phase 2)
- Rollback mechanism
- Delta updates

---

## 3. File Ownership

### Files this agent creates (new)
```
backend/routes/update.py
frontend/src/features/update/index.ts
frontend/src/features/update/types.ts
frontend/src/features/update/api.ts
frontend/src/features/update/hooks.ts
frontend/src/features/update/components/UpdateBanner.tsx
```

### Files this agent modifies (minimal, safe changes only)
```
backend/api/router.py                      ← one line: include_router(update_router)
backend/core/config.py                     ← add 3 settings fields (append only)
frontend/src/components/layout/app-shell.tsx  ← one line: render <UpdateBanner />
frontend/src/services/system.ts            ← extend SystemStatus type (additive)
frontend/src/services/index.ts             ← export updateService if needed
```

### Files this agent MUST NOT modify
```
backend/database/models.py                 ← no DB changes this sprint
backend/database/session.py
backend/services/*
backend/routes/library.py
backend/routes/reader.py
backend/routes/sources.py
backend/routes/downloads.py
backend/routes/ai.py
backend/routes/system.py                   ← read-only; update has its own router
frontend/src/features/reader/*             ← Cursor Chat 1 owns this
frontend/src/features/library/*
frontend/src/features/downloads/*
frontend/src/features/sources/*
```

---

## 4. Update Manifest Format

The manifest is a JSON file hosted at a stable public URL (configured in settings). Version comparisons use semver.

```json
{
  "schema_version": 1,
  "latest": {
    "version": "0.2.0",
    "release_date": "2026-07-15",
    "release_notes_url": "https://github.com/aistudio/releases/tag/v0.2.0",
    "download_url": "https://github.com/aistudio/releases/download/v0.2.0/AIStudio-0.2.0-windows-x64.exe",
    "download_sha256": "abc123...",
    "min_required_version": null,
    "channel": "stable"
  },
  "channels": {
    "stable": "0.2.0",
    "beta": "0.2.1-beta.1"
  }
}
```

**Field semantics:**
- `schema_version`: integer; increment when the manifest format changes incompatibly
- `latest.version`: semver string (`MAJOR.MINOR.PATCH` or `MAJOR.MINOR.PATCH-prerelease.N`)
- `latest.min_required_version`: if set and the running version is below this, the update is mandatory — show a blocking modal, not just a banner
- `latest.channel`: `"stable"` or `"beta"` — the backend only follows the configured channel
- `download_sha256`: hex SHA-256 of the installer binary (for Phase 2 verification)
- `channels`: convenience lookup; the backend uses `latest` directly

---

## 5. Backend — `routes/update.py`

### Endpoints

#### `GET /update/check`

Fetch the remote manifest, compare against current version, return a structured response.

**Response schema (Pydantic):**
```python
class UpdateCheckResponse(BaseModel):
    current_version: str           # "0.1.0"
    latest_version: str            # "0.2.0"
    update_available: bool         # True if latest > current
    mandatory: bool                # True if min_required_version > current
    release_notes_url: str | None  # link to GitHub release page
    download_url: str | None       # link to installer (Phase 1: just link, don't download)
    channel: str                   # "stable" or "beta"
    checked_at: str                # ISO-8601 UTC datetime of this check
    manifest_version: int          # schema_version from manifest
```

**Behavior:**
1. Read `settings.update_manifest_url` and `settings.update_channel`
2. Fetch the manifest with a 10-second timeout via `httpx.get()` with `follow_redirects=True`
3. Parse and validate the manifest JSON against the expected schema
4. Compare versions using `packaging.version.Version` (already installed as a setuptools dependency; do not add new pip deps without checking `requirements.txt`)
5. Return the response — **do not cache the result server-side** (caching happens in the frontend)
6. On any failure (network error, bad JSON, unexpected schema), return HTTP 200 with `update_available: false` and log the error. Never return a 5xx for an update check failure — it would break the health check pattern.

**Version comparison rule:**
```
update_available = Version(latest_version) > Version(current_version)
mandatory = (min_required_version is not None) and (Version(current_version) < Version(min_required_version))
```

**Error response (still 200):**
```json
{
  "current_version": "0.1.0",
  "latest_version": "0.1.0",
  "update_available": false,
  "mandatory": false,
  "release_notes_url": null,
  "download_url": null,
  "channel": "stable",
  "checked_at": "2026-07-01T12:00:00Z",
  "manifest_version": 0,
  "error": "Failed to reach update server"
}
```

When an `error` field is present, the frontend must treat `update_available: false` as definitive and not show a notification.

#### `GET /update/version`

Simple endpoint returning current running version. Used by frontend on startup to confirm backend is reachable and running the expected version.

**Response:**
```json
{
  "version": "0.1.0",
  "name": "AI Studio",
  "build_date": null
}
```

This endpoint never fails (no external calls). Returns the version from `settings.version`.

### Registration in `api/router.py`

Append at the end of `router.py`:
```python
from routes.update import router as update_router
api_router.include_router(update_router)
```

---

## 6. Backend — Config Changes (`core/config.py`)

Add three fields to the `Settings` class. These are **append-only** additions — do not modify any existing field:

```python
# Update system settings
update_manifest_url: str = "https://raw.githubusercontent.com/aistudio/aistudio/main/update-manifest.json"
update_channel: str = "stable"          # "stable" | "beta"
update_check_enabled: bool = True       # set False to disable update checks entirely
```

These fields can be overridden in `config/settings.json` by users who want to point to an internal update server or disable update checks.

---

## 7. Frontend — Module Structure

```
frontend/src/features/update/
├── index.ts                    ← public exports
├── types.ts                    ← TypeScript interfaces
├── api.ts                      ← HTTP calls
├── hooks.ts                    ← React hooks (polling logic)
└── components/
    └── UpdateBanner.tsx        ← notification banner UI
```

### `types.ts`

```typescript
export interface UpdateCheckResult {
  current_version: string;
  latest_version: string;
  update_available: boolean;
  mandatory: boolean;
  release_notes_url: string | null;
  download_url: string | null;
  channel: string;
  checked_at: string;
  manifest_version: number;
  error?: string;
}

export interface UpdateState {
  isChecking: boolean;
  result: UpdateCheckResult | null;
  lastChecked: Date | null;
  isDismissed: boolean;
}
```

### `api.ts`

```typescript
import { http } from "@/services/http";
import type { UpdateCheckResult } from "./types";

export const updateApi = {
  checkForUpdate: () => http.get<UpdateCheckResult>("/update/check"),
  getVersion: () => http.get<{ version: string; name: string }>("/update/version"),
};
```

### `hooks.ts`

**`useUpdateCheck` hook:**

```typescript
export function useUpdateCheck(): UpdateState
```

**Behavior:**
- Uses TanStack Query `useQuery` with key `["update", "check"]`
- `staleTime`: 4 hours (14_400_000 ms) — do not re-fetch more often than this
- `refetchInterval`: 4 hours — poll in the background while the app is open
- `refetchOnWindowFocus`: false — do not re-check just because the user switched windows
- `refetchOnMount`: true — always check on first mount
- `retry`: 0 — do not retry failed update checks; failures are expected when offline
- Returns `isDismissed` state that persists in `sessionStorage` (not localStorage — dismissed banner should reappear on app restart)

**`useUpdateActions` hook:**

```typescript
export function useUpdateActions(): {
  dismiss: () => void;
  openReleaseNotes: () => void;
}
```

`dismiss()` sets `isDismissed: true` in sessionStorage key `"aistudio-update-dismissed"`.  
`openReleaseNotes()` opens `result.release_notes_url` in a new tab via `window.open(url, "_blank", "noopener,noreferrer")`.

---

## 8. Frontend — `UpdateBanner.tsx`

### Visual spec

**Position:** Fixed bottom of screen, full width. Z-index above normal content but below any modals. Do not render inside the reader scroll container — it must be in `app-shell.tsx` at the layout level.

**Normal update (non-mandatory):**
```
┌─────────────────────────────────────────────────────────────────────┐
│  AIStudio 0.2.0 is available.  [View release notes]  [×  Dismiss]  │
└─────────────────────────────────────────────────────────────────────┘
```
- Background: `var(--color-surface-3)` or equivalent
- Text: primary text color
- "View release notes" button: outlined style, opens URL in new tab
- "× Dismiss" button: ghost style, sets `isDismissed` in sessionStorage
- Do not render if `isDismissed` is true

**Mandatory update:**
```
┌───────────────────────────────────────────────────────────────────────┐
│  ⚠ Required update: AIStudio 0.2.0 must be installed to continue.    │
│  [Download update]                                                     │
└───────────────────────────────────────────────────────────────────────┘
```
- Background: `var(--color-warning)` or amber/yellow variant
- No dismiss button (mandatory update cannot be dismissed)
- "Download update" button opens `download_url` in new tab

**Loading state:** Do not show anything while checking. The banner only appears after a successful check with `update_available: true`.

**Error state:** Do not show anything. The banner is suppressed when `result.error` is present.

### Component interface

```typescript
interface UpdateBannerProps {
  className?: string;
}

export function UpdateBanner({ className }: UpdateBannerProps): JSX.Element | null
```

Returns `null` when no update is available, when dismissed, or when there's a check error.

### Accessibility

- The banner has `role="alert"` and `aria-live="polite"` for non-mandatory updates
- Mandatory updates use `aria-live="assertive"`
- The dismiss button has `aria-label="Dismiss update notification"`
- All interactive elements are keyboard-focusable with visible focus ring

---

## 9. Integration Point — `app-shell.tsx`

The banner must be added **outside** the scrollable content area so it doesn't affect scroll calculations in the reader.

Find the outermost layout div in `app-shell.tsx` and add the banner as the last child, after the `{children}` render:

```tsx
import { UpdateBanner } from "@/features/update";

// Inside the app shell layout return:
<>
  {/* existing layout structure */}
  {children}
  <UpdateBanner />
</>
```

The `UpdateBanner` is self-contained — it manages its own query, state, and visibility. No props required at the call site.

---

## 10. Data Flow

```
App startup
  │
  └─ UpdateBanner mounts → useUpdateCheck() → TanStack Query
       │
       ├─ GET /update/check (backend)
       │     ├─ fetch settings.update_manifest_url (remote GitHub URL)
       │     ├─ parse manifest JSON
       │     ├─ compare versions
       │     └─ return UpdateCheckResponse
       │
       ├─ Cache for 4 hours (staleTime)
       ├─ Re-check every 4 hours (refetchInterval)
       │
       ├─ update_available: false → banner hidden
       ├─ error present → banner hidden
       ├─ isDismissed in sessionStorage → banner hidden
       ├─ update_available: true, not mandatory → show non-blocking banner
       └─ update_available: true, mandatory → show blocking banner
```

---

## 11. Edge Cases

| Scenario | Expected behavior |
|---|---|
| No internet connection | Backend `httpx.get()` times out; response is `update_available: false, error: "..."`. Banner hidden. |
| Manifest URL is unreachable | Same as above. Log error server-side. Never throw 5xx. |
| Manifest JSON is malformed | Backend catches `json.JSONDecodeError`, returns error response. |
| `latest_version` is same as `current_version` | `update_available: false`. Banner hidden. |
| `latest_version` is older than `current_version` | Dev build ahead of manifest. `update_available: false`. Banner hidden. |
| `update_check_enabled: false` in settings | Backend `GET /update/check` returns immediately with `update_available: false`, no manifest fetch |
| User dismisses banner then reopens browser | `sessionStorage` is cleared on browser close. Banner reappears on next session. |
| Mandatory update with no `download_url` | Show mandatory banner text but omit the download button. |
| `release_notes_url` is null | "View release notes" button is not rendered |

---

## 12. Error Handling

### Backend
- All exceptions in `GET /update/check` must be caught in a broad `try/except`
- Never let an update check crash the server or return a 5xx response
- Log errors at `WARNING` level with the manifest URL in the message
- Return a valid `UpdateCheckResponse` with `update_available: False` and an `error` string

### Frontend
- TanStack Query's `retry: 0` means a failed query stays in `error` state
- The `useUpdateCheck` hook returns `isChecking: false, result: null` in error state
- `UpdateBanner` renders nothing when `result` is null — no error UI, no loading spinner

---

## 13. Performance Considerations

- The update check is a cold HTTP call through the backend to a remote server — it must never block the UI or the reader
- `staleTime: 4 hours` means TanStack Query uses the cached result for 4 hours; the network call happens at most once per session during normal use
- The banner component must not re-render unless the query result changes — use `useUpdateCheck` as a stable hook with no side effects
- The `refetchInterval` uses TanStack Query's built-in polling — do not use `setInterval` directly

---

## 14. Security Considerations

- The manifest URL is a configured setting — it can be pointed at an internal server by organizations
- The backend fetches the manifest, not the frontend — the client never makes a direct request to GitHub or any external server
- `download_url` is opened via `window.open(url, "_blank", "noopener,noreferrer")` — the `noopener` attribute prevents the opened tab from accessing the opener's `window`
- Do not follow redirects from `download_url` in the browser — just open the URL; the user's OS handles it
- No authentication tokens or secrets are involved in the update manifest
- The manifest URL is logged at startup if `update_check_enabled: true` — ensure no secrets appear in the URL (no API keys in query params)

---

## 15. Testing Requirements

### Backend tests — `backend/tests/test_update.py`

```python
def test_get_version_returns_current_version(client):
    response = client.get("/update/version")
    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"

def test_update_check_when_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "update_check_enabled", False)
    response = client.get("/update/check")
    assert response.status_code == 200
    assert response.json()["update_available"] is False

def test_update_check_network_failure_returns_200(client, monkeypatch):
    # Patch httpx.get to raise ConnectError
    response = client.get("/update/check")
    assert response.status_code == 200
    assert response.json()["update_available"] is False
    assert "error" in response.json()

def test_update_available_when_manifest_has_newer_version(client, monkeypatch):
    # Patch httpx.get to return manifest with version "99.0.0"
    response = client.get("/update/check")
    assert response.json()["update_available"] is True
    assert response.json()["latest_version"] == "99.0.0"

def test_mandatory_flag_set_when_min_required_exceeds_current(client, monkeypatch):
    # Patch manifest: min_required_version = "99.0.0"
    response = client.get("/update/check")
    assert response.json()["mandatory"] is True
```

### Frontend tests — `frontend/src/features/update/__tests__/`

**`UpdateBanner.test.tsx`:**
- Does not render when `update_available: false`
- Does not render when `error` is present in result
- Renders non-mandatory banner when update is available
- Does not render dismiss button on mandatory update
- Calls `window.open` with correct URL on "View release notes" click
- Does not render after dismiss button click
- Has `role="alert"` on the banner element

**`hooks.test.ts`:**
- `useUpdateCheck` returns `isChecking: true` while query is pending
- `isDismissed` defaults to `false`
- `isDismissed` becomes `true` after `dismiss()` is called
- `dismiss()` writes to sessionStorage

---

## 16. Acceptance Criteria

- [ ] `npm run build` exits 0
- [ ] `npm run typecheck` exits 0
- [ ] `npm run lint` exits 0
- [ ] `pytest backend/tests/test_update.py` all pass
- [ ] All frontend tests pass
- [ ] `GET /update/version` returns `{"version": "0.1.0", "name": "AI Studio"}`
- [ ] `GET /update/check` with an unreachable manifest URL returns HTTP 200 with `update_available: false`
- [ ] `GET /update/check` with `update_check_enabled: false` returns HTTP 200 immediately (no network call)
- [ ] Mock manifest with version "99.0.0": banner appears in the app
- [ ] Clicking "× Dismiss" hides the banner
- [ ] Refreshing the page (new session) shows the banner again
- [ ] Banner is visible from all routes including `/reader/...`
- [ ] Banner does not appear inside the reader's scrollable page area
- [ ] Banner has correct ARIA attributes
- [ ] No `console.error` or TypeScript errors during normal use

---

## 17. Merge Risks

**Risk 1 — `app-shell.tsx`:**  
This is the highest-conflict file. Cursor Chat 1 may also need to verify the reader scroll container is not affected by the banner. Coordinate: the banner is `position: fixed; bottom: 0`, so it does not affect document flow or scroll container height.

**Risk 2 — `api/router.py`:**  
Other agents (Kimi) will also add to this file. Merge protocol: add `include_router(update_router)` as the last line in the file. If a merge conflict occurs, resolve by keeping all `include_router` lines in any order — there is no ordering dependency.

**Risk 3 — `core/config.py`:**  
Kimi agents and other agents may also need to add settings. The three fields added here (`update_manifest_url`, `update_channel`, `update_check_enabled`) are self-contained. Merge by appending — do not reorder existing fields.

---

## 18. Future Extensibility

- **Phase 2 — Background download:** Add `GET /update/download` that streams the installer binary (with progress) and verifies SHA-256. The `UpdateCheckResponse` already includes `download_sha256` and `download_url`.
- **Phase 3 — Silent install on Windows:** Use `subprocess.Popen` to run the installer with `/S /NORESTART` flags after download verification. Add a restart prompt in the frontend.
- **Channel switching:** `settings.json` already has `update_channel`. The manifest's `channels` field supports multiple channels. Users can switch to `"beta"` by editing `settings.json`.
- **Internal update server:** Organizations can set `update_manifest_url` to point at their own hosted JSON file — all update logic works without any code changes.
- **Offline mode:** When `useUpdateCheck` is used in an offline context, the `error` field suppresses the UI. No special handling needed.
