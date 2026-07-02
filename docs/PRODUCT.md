# AIStudio — Product Requirements Document

**Version:** 1.0 · **Status:** Living document — updated with each phase completion
**Cross-references:** [VISION.md](VISION.md) · [ROADMAP.md](ROADMAP.md) · [PROJECT_RULES.md](PROJECT_RULES.md)

---

## 1. Product Overview

### 1.1 What AIStudio is

AIStudio is a local-first, AI-powered desktop application for reading, organizing,
and creating Manhwa, Manga, and Manhua. It runs on the user's own hardware. All
processing — scanning, reading, AI analysis, image generation — happens locally with
no cloud required and no data leaving the machine.

It is the operating system for a personal comic library. Not a reader with extras.
A complete platform with a reader as one of its pillars.

### 1.2 What problem it solves

The manhwa/manga reading ecosystem is fragmented. A serious reader today uses:
- One tool to download content.
- Another to organize it.
- A third to read it.
- External cloud AI (ChatGPT, NotebookLM) to discuss and understand it.
- No tool at all to create their own.

None of these tools know about each other. Progress in one does not inform the others.
AI tools have no context about the user's specific library. Organization tools have no
reading experience. Readers have no AI understanding.

AIStudio is the single application where all of these happen, sharing one data model.

### 1.3 Elevator pitch

> *For manhwa and manga readers who want to own their experience, AIStudio is a
> local-first platform that combines a professional library manager, a fast reader,
> and local AI intelligence into one application. Unlike cloud-based tools, AIStudio
> runs entirely on your hardware — your collection stays yours, AI runs on your GPU,
> and nothing requires an internet connection.*

---

## 2. Target Audience

### 2.1 Primary audience

**Serious manhwa/manga readers** who:
- Have large personal libraries (hundreds to thousands of series).
- Care about organization, metadata, and reading statistics.
- Want AI features without giving their data to cloud services.
- Use Windows as their primary OS.
- Are comfortable with a technical setup (running local servers, Ollama).

### 2.2 Secondary audience

- **Manhwa/manga creators** who want AI tools for worldbuilding and image generation.
- **Content archivists** who download and preserve series and want professional organization.
- **Developers** building on top of the platform via the future plugin API.

### 2.3 Anti-audience (who this is not for)

- Casual readers who want a simple "open a file and read it" experience.
- Users who want a cloud-hosted, zero-setup solution.
- Users without technical comfort running local services.
- Users who want a mobile-native app (Phase 6 adds mobile web; native is not planned).

---

## 3. User Personas

### Persona 1 — The Power Reader ("Yoongi")

**Background:** 28 years old. Has been reading manhwa for 10 years. Downloads everything
and stores it locally. Currently uses a combination of Kavita (library), a basic reader,
and ChatGPT (for discussing stories) — three separate tools.

**Goals:**
- One place for everything.
- Never lose track of where they are in 300 active series.
- Find any chapter or scene they vaguely remember.
- Discuss story theories with an AI that actually knows their library.

**Pain points:**
- Can't search inside chapters. Can only search titles.
- ChatGPT doesn't know their specific library — has to re-explain context every time.
- Reading progress is siloed per app. Starting fresh after switching readers.
- Character tracking is manual (they keep a spreadsheet).

**What AIStudio does for them:**
- OCR + semantic search finds "the chapter where the hunter awakens in the dungeon."
- AI chat already has context from their library — no re-explaining.
- Reading progress is unified and persistent.
- Character database is built automatically from OCR text.

---

### Persona 2 — The AI Explorer ("Mia")

**Background:** 34 years old. Software developer. Reads manhwa and is fascinated by
AI tools. Uses NotebookLM for book clubs but wishes it could index her manhwa library.
Wants to "talk to her library" — ask questions, get timelines, understand character arcs.

**Goals:**
- Get AI summaries without spoilers for unread chapters.
- Ask questions like "explain the power system in Solo Leveling."
- See a timeline of events across 200 chapters automatically generated.
- Track which characters appear together across the series.

**Pain points:**
- NotebookLM can't read images. Manga/manhwa is images.
- Cloud AI doesn't know her specific collection.
- Generating summaries manually (copy-paste screenshots into ChatGPT) is tedious.
- Timeline tracking in a spreadsheet is a part-time job.

**What AIStudio does for them:**
- OCR extracts all dialogue; AI builds the timeline from text.
- Chapter summaries generated automatically after OCR.
- "Ask this series" chat with full context from summaries and OCR.
- Character appearance tracking from extracted names.

---

### Persona 3 — The Archivist ("Chen")

**Background:** 40 years old. Has collected manhwa for 15 years. Has ~5,000 series
organized in elaborate folder structures. Runs a NAS. Cares deeply about metadata:
correct titles, covers, author information, tags.

**Goals:**
- Perfect metadata on everything in the library.
- Automatic cover generation for series without one.
- Collections that group series by theme, author, or era.
- Everything works on his NAS — accessible from multiple devices.

**Pain points:**
- Metadata tools are built for Western comics or books, not manhwa.
- Covers for his older series are missing or low quality.
- Collections in existing tools don't sync between devices.
- NAS setup with existing tools is fragile and poorly documented.

**What AIStudio does for them:**
- AI generates metadata (description, tags, genre) from OCR content.
- Cover generation from first page of each series.
- Collections with rich descriptions, stored in the database.
- NAS deployment (Phase 6) with multi-device reading progress sync.

---

### Persona 4 — The Creator ("Seo-yeon")

**Background:** 22 years old. Art student. Writes and draws her own manhwa. Uses
reference images for character design, plans chapters in a notebook, and generates
concept art with AI tools. Currently uses separate tools for everything.

**Goals:**
- Manage character sheets, world bibles, and chapter outlines in one place.
- Generate reference images from text prompts using local diffusion models.
- Plan panel layouts before committing to drawing.
- Export finished chapters as CBZ for distribution.

**Pain points:**
- Character reference images are scattered across folders.
- ComfyUI is powerful but has no integration with the story context.
- World-building notes are in a separate wiki with no connection to the art.
- No good panel planning tool that works with AI generation.

**What AIStudio does for them:**
- Creation Studio workspace: character sheets, world bible, chapter outlines in one app.
- ComfyUI integration for in-context image generation.
- Panel planning with AI-assisted layout suggestions.
- Export to CBZ — the created series appears in the Library automatically.

---

## 4. Main Screens

### 4.1 Library

The primary screen. A grid of series covers with title, chapter count, and reading
progress indicator. Supports:
- Search (title, author, tag) and sort (title, author, last read, date added).
- Filter by collection, tag, category, reading status (reading, completed, on hold).
- "Continue Reading" strip at the top: the user's in-progress series.
- Favorites rail.
- Import dialog (folder path input + progress display).
- Right-click / keyboard actions: edit metadata, add to collection, mark as read, delete.

### 4.2 Series Detail

Opens from a Library card. Shows:
- Cover, title, author, description, tags, status.
- Chapter list with read/unread state, chapter numbers, dates.
- Reading statistics (time spent, pages read, completion percentage).
- AI section (summaries, character list, timeline link) — populated after Phase 3.
- "Continue Reading" and "Start from Beginning" actions.

### 4.3 Reader

Full-screen reading experience. Two modes:
- **Webtoon mode:** vertical infinite scroll, full-width images. Default for manhwa.
- **Manga mode:** single page with left/right navigation. Supports right-to-left and double-page.

Controls overlay (appears on hover or key press):
- Mode switcher, zoom control, chapter progress bar.
- Bookmark button, chapter navigator, settings.
- Keyboard shortcut reference.

### 4.4 Search

A dedicated search surface. Two modes:
- **Quick search:** title, author, tag matching. Always available.
- **Deep search (Phase 3):** semantic + OCR text search. Requires prior indexing.

Results are grouped by type: Series, Chapters, Characters, Scenes.

### 4.5 AI Chat (Phase 3)

Per-series AI conversation interface. The chat context includes:
- OCR-extracted text from all chapters.
- AI-generated summaries.
- Character database.
- Timeline.

Chat history is persisted per series. Users can ask about story, characters, lore,
or ask for explanations of confusing chapters.

### 4.6 Knowledge Graph (Phase 4)

A structured view of everything the AI has learned about a series:
- **Characters tab:** profile cards, relationship graph visualization.
- **World tab:** locations, factions, lore entries.
- **Timeline tab:** chronological event list, editable.
- **Story tab:** scenes, plot points, revelations, foreshadowing.

All content is user-editable. AI output is a starting point.

### 4.7 Creation Studio (Phase 5)

A workspace for creating original manhwa:
- **Project overview:** series metadata, character roster, chapter list.
- **Character editor:** appearance, traits, voice, reference images.
- **World editor:** locations, rules, factions.
- **Chapter planner:** scene list, dialogue notes, panel layout grid.
- **Image generator:** ComfyUI-backed generation with series context injection.
- **Asset library:** all generated images organized by character and scene.
- **Export:** CBZ, PDF, image folder.

### 4.8 Settings (Phase 6)

- Library paths (add/remove root directories, set scan interval).
- AI model configuration (which model for each task, per-task overrides).
- Reader defaults (default mode, zoom level, pre-fetch size).
- Background task management (pause/resume OCR, embedding, thumbnail queues).
- Database management (stats, vacuum, backup, PostgreSQL migration).

---

## 5. User Workflows

### 5.1 Library import workflow

1. User opens AIStudio for the first time.
2. Empty library state prompts to import a folder.
3. User opens Import dialog, enters or pastes a folder path.
4. Backend starts background scan. Library page shows a progress indicator.
5. As series are detected, they appear in the grid in real time (WebSocket push).
6. After the scan completes, covers are generated in a second background pass.
7. User sees their full library within minutes.
8. Folder watcher is set up — future changes to the folder appear automatically.

**Edge cases handled:**
- Folder doesn't exist → clear error message, no crash.
- Folder is already imported → scan is incremental, no duplicates.
- Mixed formats (folders + CBZ) → both detected and imported correctly.

---

### 5.2 Reading workflow

1. User sees their library grid.
2. "Continue Reading" strip shows in-progress series with last-chapter progress.
3. User clicks a series card → Series Detail page.
4. User clicks "Continue Reading" or a specific chapter → Reader opens.
5. Reader shows pages in webtoon mode (vertical scroll) by default.
6. Progress is auto-saved every 5 pages and on chapter close.
7. At end of chapter, "Next Chapter" button / shortcut appears.
8. User can switch to manga mode, zoom, bookmark, or toggle controls with keyboard.
9. Pressing Esc exits reader, returns to Series Detail at the last scroll position.

**Keyboard shortcuts (reader):**
- `j` / `↓` — scroll down (webtoon) / next page (manga)
- `k` / `↑` — scroll up (webtoon) / previous page (manga)
- `→` / `l` — next chapter
- `←` / `h` — previous chapter
- `m` — toggle webtoon / manga mode
- `b` — bookmark current page
- `f` — toggle full screen
- `Esc` — exit reader
- `?` — show shortcut reference

---

### 5.3 AI analysis workflow (Phase 3)

1. User imports a series (library workflow above).
2. After scan completes, user clicks "Analyze with AI" on the Series Detail page.
3. OCR queue starts processing pages. Progress bar shows "X of N pages indexed."
4. After OCR, embedding and summary queues run automatically.
5. User receives a notification when analysis is complete.
6. Series Detail now shows: chapter summaries, extracted characters, timeline preview.
7. User opens AI Chat tab, asks: "Who are the main characters and what are their goals?"
8. AI responds with context from the summaries and character database.
9. User can continue the conversation, ask follow-up questions, or request a character list.

---

### 5.4 Search workflow

**Quick search (available immediately):**
1. User presses `/` from any screen.
2. Search input focuses; user types a title, author, or tag.
3. Results appear in real time (client-side filter for already-loaded data, API call for large libraries).
4. User selects a result → goes to Series Detail or Reader as appropriate.

**Semantic search (Phase 3, requires prior AI analysis):**
1. User switches to "Deep Search" mode in the Search pillar.
2. Types a natural language query: "the chapter where the guild leader betrays everyone."
3. Backend performs FTS5 text search and vector similarity search against OCR corpus.
4. Results show matching chapters with the relevant passage highlighted.
5. User clicks a result → Reader opens at that chapter.

---

### 5.5 Creation workflow (Phase 5)

1. User opens Create pillar, clicks "New Project."
2. Names the project, selects a genre and format (manhwa/manga).
3. Project workspace opens with empty character roster and world bible.
4. User creates characters: name, description, traits, reference images (AI-generated or uploaded).
5. User writes a chapter outline: scene list with notes.
6. User opens the Panel Planner for Chapter 1, arranges a panel layout grid.
7. For each panel, user writes a prompt → generates image via ComfyUI.
8. Generated image appears in the panel; user approves or regenerates.
9. Completed chapter exported as CBZ.
10. The project appears in the Library as a series with "Created" badge.

---

### 5.6 Download workflow (Phase 6)

1. User adds a source URL to the Download Manager.
2. Download Manager queues the series, fetches metadata and chapter list.
3. Downloads proceed in the background, respecting rate limits.
4. Each completed download is added to the library scan queue.
5. Within minutes of a chapter downloading, it appears in the Library.
6. User can pause, resume, or cancel individual downloads or the full queue.
7. Download history shows all past downloads with timestamps and status.

---

## 6. Future Vision

The long-term trajectory of AIStudio across three horizons:

### Near-term (Phases 2–3)
A fully functional local library + reader with AI understanding. Users can import their
entire existing collection, read comfortably, and have AI conversations about any series.
This is the minimum viable product that replaces a combination of Kavita + ChatGPT for
the target user.

### Medium-term (Phases 4–5)
A knowledge platform and creation tool. Users don't just read — they understand, annotate,
and create. The Knowledge Graph makes AIStudio irreplaceable for serious readers. The
Creation Studio opens the platform to creators.

### Long-term (Phase 6+)
A platform with a plugin ecosystem, multi-user NAS deployment, and optional cloud sync
for reading progress. The open API enables community-built sources, themes, and
integrations. AIStudio becomes the de facto standard for self-hosted manga infrastructure.

---

## 7. Competitive Analysis

### 7.1 Kavita

**What it does:** A self-hosted reading server for manga, manhwa, comics, and books.
Excellent library management, multi-user support, reading progress sync, OPDS/Kobo support.

**Strengths:** Mature, feature-rich library management. Good metadata support. Active
development. Strong multi-user implementation.

**Limitations:** No AI features of any kind. No creation tools. No semantic search.
Reader is adequate but not exceptional. Requires a server setup separate from the client.

**How AIStudio surpasses it:** Every Kavita library feature plus AI understanding, semantic
search, character databases, timeline generation, and creation tools — in a single
application rather than a client-server split.

---

### 7.2 Komga

**What it does:** Self-hosted manga/comic server. Focus on comics/Western format. REST
API, OPDS support, reading progress, collections.

**Strengths:** Excellent API design. Good for comics infrastructure. Works well with
third-party clients (Tachiyomi, etc.).

**Limitations:** Not optimized for webtoon/manhwa. No AI. No creation. No semantic
search. Purely a library server — reading experience depends on third-party clients.

**How AIStudio surpasses it:** Native webtoon-first reading experience (vertical scroll
mode), integrated AI, semantic search, and creation tools. Also self-contained — no
need to configure a separate client.

---

### 7.3 Mihon / Tachiyomi

**What it does:** Android manga reader. Supports hundreds of sources (online and local).
Excellent mobile reading experience. Tracking integrations.

**Strengths:** The best mobile reading UX. Source plugins cover almost every provider.
Tracking with AniList, MyAnimeList, Kitsu.

**Limitations:** Android-only. No local AI. No creation tools. No library management
beyond the reading app. No desktop experience.

**How AIStudio surpasses it:** Desktop-first (where creators and power readers work).
Local AI integration. Creation Studio. Knowledge Graph. The web-responsive reader in
Phase 6 provides a comparable mobile reading experience without requiring Android.

---

### 7.4 Calibre

**What it does:** The standard for ebook library management. Excellent metadata editing,
format conversion, device sync, and plugin ecosystem.

**Strengths:** Extremely mature (15+ years). Unmatched metadata tools for books. Robust
plugin system. Works on all platforms.

**Limitations:** Built for text-based books, not image-based comics. Comic reading in
Calibre is an afterthought. No AI. Performance degrades with large image collections.
The UI shows its age.

**How AIStudio surpasses it:** Image-native from the ground up. Built for panels and
pages, not paragraphs. Reading experience is a first-class pillar, not a plugin. AI
understands visual content via OCR and panel analysis.

---

### 7.5 Jellyfin

**What it does:** Self-hosted media server for movies, TV, music. Excellent multi-user
library management, transcoding, clients for all platforms.

**Philosophy parallel:** AIStudio deliberately inherits Jellyfin's library management
philosophy: smart folders, metadata matching, poster/backdrop management, watching
progress, multi-library support.

**Limitations:** Video-first; comics are a plugin afterthought. No reading experience.
No AI understanding. No creation tools. Transcoding overhead not applicable to images.

**How AIStudio surpasses it in the comics domain:** Comic-native architecture (images
served as-is, not transcoded). AI understanding of visual content. Creation tools.
Knowledge Graph. The Jellyfin philosophy of "your media, your server" is preserved and
extended with AI intelligence.

---

### 7.6 Summary: AIStudio's unique position

No existing tool combines:
1. Professional library management (Kavita level).
2. Fast, mode-aware reading (Tachiyomi mobile UX, desktop).
3. Local AI intelligence (OCR, summaries, semantic search, Q&A).
4. Knowledge Graph (Obsidian-style, connected to content).
5. Creation Studio (ComfyUI-backed image generation + story tools).

AIStudio is the only application that treats these as one integrated product
rather than five separate tools stitched together by the user.

---

## 8. Success Metrics

These are the measures that indicate the product is achieving its mission:

| Metric | Target (Phase 2) | Target (Phase 4) |
|--------|-----------------|-----------------|
| Time to first reading session after import | < 5 minutes | < 2 minutes |
| Library load time (500 series) | < 500ms | < 200ms |
| Reader: time to first page visible | < 200ms | < 100ms |
| Search: results for title query | < 100ms | < 50ms |
| AI analysis: time to start reading again (post-queue) | N/A (Phase 3) | Immediate |
| Build pass rate | 100% | 100% |
| Zero hardcoded colors in UI | 100% | 100% |

---

## 9. Out of Scope (Explicitly)

The following are **not** part of AIStudio and will not be added without a deliberate
architectural decision and documentation:

- **Cloud hosting or SaaS model.** AIStudio is a local-first tool. Always.
- **Built-in content scraping** for sites that prohibit it.
- **DRM circumvention** tools of any kind.
- **Social features** (follows, comments, community) in the single-user model.
- **Light mode.** The application is dark-theme-only. The design system does not
  support a light theme toggle.
- **Paid features or subscriptions.** The platform is open source.
