# AIStudio — Product Vision

## What this is

AIStudio is a local-first, AI-powered platform for reading, organizing, and creating
Manhwa, Manga, and Manhua. It runs entirely on the user's own hardware. No cloud
required. No accounts required. No internet required after setup.

It is not a manga reader. It is the operating system for a personal comic library.

---

## The problem it solves

Existing tools each solve one part of the problem:

| Tool | What it does well | What it misses |
|------|-------------------|----------------|
| Kavita / Komga | Library server, reading | No AI, no creation, no deep metadata |
| Mihon / Tachiyomi | Mobile reading, sources | Mobile-only, no local AI, no creation |
| Calibre | Library management, metadata | Book-centric, not built for manga/webtoons |
| Jellyfin | Media library UX, multi-user | Video-centric, no reading, no AI |
| Obsidian | Knowledge graph, linking | Not for comics; no reading or library |
| ChatGPT / NotebookLM | AI Q&A, summarization | Cloud-only, no library integration |
| Character.AI | AI character interaction | Cloud-only, no library context |
| VS Code | Workspace philosophy | Not for media |

None of them combine into a coherent product. AIStudio does.

---

## The full platform

### Library
Everything Kavita and Komga do, plus more.

- Import unlimited series from local folders, archives (.cbz, .zip), or PDFs.
- Auto-detect series → volume → chapter → page hierarchy from folder structure.
- Auto-generate covers from first pages.
- Collections, tags, categories, favorites.
- Continue reading across all series.
- Reading statistics and history.
- Background folder watching — new files appear automatically.
- Support for images, CBZ/CBR/ZIP/RAR archives, and PDF.

### Reader
The fastest possible reading experience.

- Vertical webtoon mode (the primary mode for manhwa).
- Traditional manga mode (right-to-left, page-by-page).
- Double-page mode for physical scans.
- Smooth scrolling, hardware-accelerated rendering.
- Zoom with pinch / scroll.
- Bookmarks per chapter.
- Full keyboard control.
- Pre-fetch next chapter.
- Remember scroll position per chapter.

### AI (all local via Ollama)
Every AI feature uses the user's own models. Nothing leaves the machine.

**Understanding the content:**
- OCR — extract dialogue from images; build a searchable text corpus.
- Summarization — per-chapter and per-series summaries.
- Character extraction — detect character names from dialogue and narration.
- Relationship mapping — who interacts with whom and how.
- Timeline generation — automatically build a chronological event timeline.
- World memory — extract locations, factions, rules, lore.
- Sentiment analysis — track character emotional arcs.

**Interaction:**
- Ask questions about any series ("Who is Sung Jin-woo's first ally?").
- Explain confusing chapters in plain language.
- Chat with a character in their voice using character memory.
- Recommend similar series from your own library.

**Generation:**
- Auto-generate metadata (genre, tags, description) for imported series.
- Generate missing covers.
- Translate untranslated text from OCR output.

### Search
Beyond simple title matching.

- Full-text search across titles, authors, tags, synopses.
- Dialogue search via OCR corpus (search inside the panels).
- Semantic search — find scenes by meaning, not keywords.
- Natural language search ("chapters where the protagonist loses a fight").
- Character search — find every chapter a character appears in.
- Search across AI summaries and extracted metadata.

### Knowledge Graph (Obsidian philosophy)
A living, interconnected database of everything the AI discovers.

- Character profiles: appearance, traits, relationships, arc summaries.
- Story database: scenes, plot points, revelations, foreshadowing.
- World map: locations, factions, power systems, rules.
- Timeline: chronological event list across chapters, with conflicts highlighted.
- Relationship graph: interactive visualization of character connections.
- All data is editable and correctable by the user.

### Creation Studio (VS Code philosophy)
For people who make comics, not just read them.

- Project workspace: character sheets, world bible, chapter outlines.
- Panel planning: script → storyboard layout.
- Image generation via ComfyUI and local diffusion models.
- Reference management: mood boards, character reference images.
- Export: CBZ, PDF, folder structure.

### Downloads (future)
For sourced content.

- Download manager with queue, resume, and retry.
- Automatic organization by series, volume, chapter.
- Metadata and cover fetching.
- Progress tracking.

---

## Long-term targets

| Area | Target |
|------|--------|
| Library scale | 100,000+ chapters, millions of images |
| Background processing | Non-blocking; always usable while indexing |
| Performance | < 100ms page load in reader; instant search results |
| Offline | Fully functional without network |
| Platform | Windows primary; NAS, Linux, macOS later |
| Users | Single-user now; multi-user later |
| Clients | Web app primary; mobile app later |
| Extensibility | Plugin/extension API in the long term |
| AI models | Any Ollama-compatible model; user configures per task |

---

## What this is not

- It is not a scraper or download tool for sites that prohibit it.
- It is not a streaming service — the user owns and hosts their own content.
- It is not a cloud application — the local hardware is the server.
- It is not a social platform — reading is personal, not shared (initially).

---

## Design philosophy

**Local-first.** The app works at full capability with no internet. Network features are additive, never required.

**Working code ships.** A usable feature beats a perfect plan. Every phase delivers something real the user can touch.

**AI improves, not replaces.** Navigation, browsing, and reading work perfectly without AI. AI enhances the experience on top of a solid foundation.

**One product, not a patchwork.** Every feature shares the same data model, design language, and keyboard grammar. Library data feeds the Reader, feeds AI, feeds Search, feeds the Knowledge Graph.

**Keyboard-first.** Power users should be able to operate the entire application without a mouse. Every action has a shortcut or can get one.

**Beautiful defaults.** The application should look and feel like a commercial product from day one, not a developer prototype.
