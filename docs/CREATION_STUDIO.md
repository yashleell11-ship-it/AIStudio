# AIStudio — Creation Studio Architecture

**Status:** Phase 5 design. Do not implement until Phase 4 (Knowledge Graph) ships.
**Cross-references:** [VISION.md](VISION.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [DATABASE.md](DATABASE.md) · [AI_PIPELINE.md](AI_PIPELINE.md) · [API.md](API.md)

---

## 1. What Creation Studio Is

AIStudio is built around a loop: read → understand → create. The Reading Library
and Knowledge Graph represent the first two turns. Creation Studio closes the loop.

A user who has read 300 manhwa series has internalized tropes, character archetypes,
panel rhythms, and visual language. Creation Studio puts a professional-grade
production toolchain in front of that knowledge. The ambition is not "AI generates
a comic for you" — it is "AI is your studio team."

**What Creation Studio replaces:**
- A separate script editor (Final Draft, Scrivener)
- A storyboarding tool (Procreate thumbnails, index cards)
- A prompt engineering workspace (Automatic1111, ComfyUI UI)
- A reference management system (Pinterest boards, Notion)
- An asset organizer (folder trees, manual naming conventions)
- A production tracker (spreadsheets, Trello boards)

**What it does not replace:** A skilled artist. The output quality ceiling is set
by the user's models, LoRAs, and creative direction.

---

## 2. Guiding Principles

### Script first, image second

The script is the source of truth. Images are rendered from script. A panel that
does not have a stage direction cannot be sent to generation. This prevents the
trap of generating random images and assembling them into a story retroactively —
which produces incoherent narratives.

The data model enforces this: `project_panels` have a `stage_direction` field that
is required before a `generation_job` can be queued.

### Composition over monolithic prompts

A panel image is always the composition of five independent layers:

```
[quality/style]  +  [character(s)]  +  [action/scene]  +  [camera]  +  [lighting]
    ↑                    ↑                   ↑                ↑              ↑
Style Profile      Character Creator     Scene Planner    Scene Planner   Style Profile
```

Each layer is independently reusable, editable, and versioned. The Prompt Manager
assembles them at generation time. This avoids the monolithic "giant string" approach
that makes prompts impossible to iterate.

### Visual consistency is a system, not a setting

The hardest problem in AI-generated sequential art is making the same character look
identical across panel 1 and panel 847. This is solved architecturally, not by hoping
the model is consistent. Every character has:
- A **canonical prompt template** (the written description that anchors identity)
- An **expression library** (pre-generated reference faces)
- An optional **LoRA** (a fine-tuned weight file that bakes in the appearance)

No character exists in a panel without at least the canonical prompt template.

### The library is the audience

Finished projects export to the Reading Library as a first-class series. The user
reads their own work alongside their imported series, with the same reader, the same
keyboard shortcuts, and the same progress tracking. Creation and consumption share
one data model and one UX.

### One tool for all models

The generation backend is model-agnostic at the service layer. The model-specific
differences (Flux's no-negative-prompt architecture, SDXL's 77-token CLIP limit,
SD 1.5's checkpoint fragmentation) are encapsulated in workflow templates stored in
the database. Adding a new model family = adding a new workflow template, not
changing service code.

---

## 3. Component Map

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           PROJECT MANAGEMENT                            │
│           (lifecycle, chapter kanban, export, library sync)             │
└───────────────────┬─────────────────────────────────────────────────────┘
                    │ owns
   ┌────────────────▼──────────────────────────────────────────────┐
   │                    STORY GENERATOR                            │
   │         Project → Arcs → Chapters → Scenes → Panels          │
   │                    (the script)                               │
   └────┬──────────────┬──────────────────────────────────────────┘
        │ who          │ where / mood
        ▼              ▼
   ┌─────────┐   ┌──────────────┐     ┌──────────────────┐
   │CHARACTER│   │SCENE PLANNER │     │  STYLE MANAGER   │
   │ CREATOR │   │ (storyboard) │     │ (visual language) │
   └────┬────┘   └──────┬───────┘     └────────┬─────────┘
        │               │                      │
        └───────────────▼──────────────────────┘
                        │ all three feed into
                ┌───────▼────────┐
                │ PROMPT MANAGER │
                │  (assembler)   │
                └───────┬────────┘
                        │ final prompt
          ┌─────────────▼──────────────┐
          │  ComfyUI INTEGRATION       │
          │    + FLUX INTEGRATION      │
          └─────────────┬──────────────┘
                        │ generated images
                ┌───────▼────────┐
                │  ASSET LIBRARY │
                └────────────────┘
```

---

## 4. Data Model

All Creation Studio tables are Phase 5. They extend the existing schema in
`DATABASE.md` without modifying any Phase 2–4 tables.

### 4.1 Projects

```sql
CREATE TABLE creation_projects (
    id                  INTEGER     PRIMARY KEY,
    title               TEXT        NOT NULL,
    genre               TEXT,
    format              TEXT        NOT NULL DEFAULT 'webtoon',
    -- format: 'webtoon' | 'manhwa_color' | 'manga_bw' | 'western_color'
    synopsis            TEXT,
    themes              TEXT,
    tone                TEXT,
    target_audience     TEXT,
    status              TEXT        NOT NULL DEFAULT 'draft',
    -- status: 'draft' | 'in_progress' | 'review' | 'published'
    style_profile_id    INTEGER     REFERENCES style_profiles(id) ON DELETE SET NULL,
    output_library_id   INTEGER     REFERENCES libraries(id) ON DELETE SET NULL,
    series_id           INTEGER     REFERENCES series(id) ON DELETE SET NULL,
    -- series_id: set after first export; links project to reading library
    panel_count         INTEGER     NOT NULL DEFAULT 0,   -- denormalized
    panels_scripted     INTEGER     NOT NULL DEFAULT 0,   -- denormalized
    panels_generated    INTEGER     NOT NULL DEFAULT 0,   -- denormalized
    panels_approved     INTEGER     NOT NULL DEFAULT 0,   -- denormalized
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 Story Structure

```sql
-- Story arcs (acts): the high-level narrative shape
CREATE TABLE story_arcs (
    id                  INTEGER     PRIMARY KEY,
    project_id          INTEGER     NOT NULL REFERENCES creation_projects(id) ON DELETE CASCADE,
    title               TEXT        NOT NULL,
    arc_type            TEXT        NOT NULL DEFAULT 'rising_action',
    -- arc_type: 'setup' | 'rising_action' | 'climax' | 'falling_action' | 'resolution'
    synopsis            TEXT,
    sequence_order      INTEGER     NOT NULL DEFAULT 0,
    chapter_count       INTEGER     NOT NULL DEFAULT 0,
    is_ai_generated     INTEGER     NOT NULL DEFAULT 0,
    is_user_edited      INTEGER     NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Chapter outlines within an arc
CREATE TABLE project_chapters (
    id                  INTEGER     PRIMARY KEY,
    project_id          INTEGER     NOT NULL REFERENCES creation_projects(id) ON DELETE CASCADE,
    arc_id              INTEGER     REFERENCES story_arcs(id) ON DELETE SET NULL,
    number              REAL        NOT NULL,
    sort_key            TEXT        NOT NULL,
    title               TEXT,
    synopsis            TEXT,
    notes               TEXT,
    status              TEXT        NOT NULL DEFAULT 'draft',
    -- status: 'draft' | 'scripted' | 'storyboarded' | 'generating' | 'generated' | 'approved'
    panel_count         INTEGER     NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Scenes group panels within a chapter
CREATE TABLE project_scenes (
    id                  INTEGER     PRIMARY KEY,
    project_id          INTEGER     NOT NULL REFERENCES creation_projects(id) ON DELETE CASCADE,
    chapter_id          INTEGER     NOT NULL REFERENCES project_chapters(id) ON DELETE CASCADE,
    sequence_order      INTEGER     NOT NULL DEFAULT 0,
    scene_type          TEXT        NOT NULL DEFAULT 'standard',
    -- scene_type: 'standard' | 'action' | 'dialogue' | 'establishing' | 'montage' | 'splash'
    setting_description TEXT,
    mood                TEXT,
    lighting_notes      TEXT,
    time_of_day         TEXT,
    panel_count         INTEGER     NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Panels: the atomic unit of creation
CREATE TABLE project_panels (
    id                      INTEGER     PRIMARY KEY,
    project_id              INTEGER     NOT NULL REFERENCES creation_projects(id) ON DELETE CASCADE,
    chapter_id              INTEGER     NOT NULL REFERENCES project_chapters(id) ON DELETE CASCADE,
    scene_id                INTEGER     REFERENCES project_scenes(id) ON DELETE SET NULL,
    panel_number            INTEGER     NOT NULL,
    sequence_order          INTEGER     NOT NULL,

    -- Layout (webtoon: width=100%, height varies; manga: grid cell)
    panel_type              TEXT        NOT NULL DEFAULT 'standard',
    -- panel_type: 'standard' | 'wide' | 'tall' | 'splash' | 'inset'
    layout_json             TEXT,
    -- layout_json: {"x":0,"y":0,"w":12,"h":8} (grid units, 12-col grid per page)

    -- Script layer — required before generation
    stage_direction         TEXT        NOT NULL DEFAULT '',
    -- stage_direction: "Jin-woo stands alone before the gate, looking up, ominous atmosphere"
    camera_angle            TEXT        NOT NULL DEFAULT 'medium',
    -- camera_angle: 'extreme_close_up' | 'close_up' | 'medium' | 'wide' | 'extreme_wide'
    --               | 'overhead' | 'worm_eye' | 'dutch_angle'
    foreground_notes        TEXT,
    background_notes        TEXT,
    dialogue_text           TEXT,
    -- raw dialogue; exported as overlay in final CBZ or embedded in image
    sound_effect_text       TEXT,
    transition_from_prev    TEXT        NOT NULL DEFAULT 'action_to_action',
    -- McCloud transition types: 'moment_to_moment' | 'action_to_action' |
    --   'subject_to_subject' | 'scene_to_scene' | 'aspect_to_aspect' | 'non_sequitur'

    -- Generation state
    generation_status       TEXT        NOT NULL DEFAULT 'empty',
    -- 'empty' | 'prompt_ready' | 'queued' | 'generating' | 'generated' | 'approved' | 'rejected'
    final_asset_id          INTEGER,
    -- INTEGER, not a FK — avoids circular reference with generated_assets (see DATABASE.md §4.22)
    rejected_reason         TEXT,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(chapter_id, panel_number)
);
CREATE INDEX idx_project_panels_chapter ON project_panels(chapter_id, sequence_order);
CREATE INDEX idx_project_panels_status ON project_panels(project_id, generation_status);
```

### 4.3 Characters

```sql
CREATE TABLE project_characters (
    id                          INTEGER     PRIMARY KEY,
    project_id                  INTEGER     NOT NULL REFERENCES creation_projects(id) ON DELETE CASCADE,

    -- Narrative layer
    name                        TEXT        NOT NULL,
    role                        TEXT        NOT NULL DEFAULT 'supporting',
    -- role: 'protagonist' | 'antagonist' | 'deuteragonist' | 'supporting' | 'minor'
    age_appearance              TEXT,
    gender_presentation         TEXT,
    personality_notes           TEXT,
    backstory_notes             TEXT,

    -- Visual layer
    appearance_description      TEXT        NOT NULL DEFAULT '',
    -- Full prose description: "tall male, late teens, black spiky hair, silver eyes,
    --   black hunter uniform with gold trim, lean athletic build"
    prompt_template             TEXT        NOT NULL DEFAULT '',
    -- Image-gen optimized: "1boy, black hair, silver eyes, black jacket, gold trim,
    --   slim build, hunter uniform, manhwa style"
    negative_prompt_fragment    TEXT        NOT NULL DEFAULT '',
    -- Character-specific negatives: "wrong hair color, beard, eyeglasses"

    -- LoRA
    lora_path                   TEXT,
    lora_weight                 REAL        NOT NULL DEFAULT 0.85,

    -- Assets
    cover_asset_id              INTEGER,    -- FK to generated_assets (not enforced to avoid cycle)
    expression_sheet_asset_id   INTEGER,    -- FK to generated_assets

    -- Import link (character imported from reading library Knowledge Graph)
    source_character_id         INTEGER     REFERENCES characters(id) ON DELETE SET NULL,

    created_at                  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Expression library: pre-generated face reference per emotion
CREATE TABLE character_expressions (
    id              INTEGER     PRIMARY KEY,
    character_id    INTEGER     NOT NULL REFERENCES project_characters(id) ON DELETE CASCADE,
    expression_name TEXT        NOT NULL,
    -- 'neutral' | 'happy' | 'sad' | 'angry' | 'surprised' | 'determined'
    -- | 'smirk' | 'fearful' | 'disgusted' | 'embarrassed' | 'calm' | custom
    prompt_modifier TEXT        NOT NULL DEFAULT '',
    -- Text to append to character's base prompt: "smiling broadly, eyes crinkled"
    asset_id        INTEGER,    -- generated_assets reference (not FK)
    is_default      INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(character_id, expression_name)
);

-- Which characters appear in which panel (with position and expression)
CREATE TABLE panel_characters (
    panel_id            INTEGER     NOT NULL REFERENCES project_panels(id) ON DELETE CASCADE,
    character_id        INTEGER     NOT NULL REFERENCES project_characters(id) ON DELETE CASCADE,
    sequence_order      INTEGER     NOT NULL DEFAULT 0,
    position            TEXT        NOT NULL DEFAULT 'center',
    -- position: 'left' | 'center' | 'right' | 'background_left' | 'background_right'
    expression_id       INTEGER     REFERENCES character_expressions(id) ON DELETE SET NULL,
    action_note         TEXT,
    -- e.g., "reaching out, expression of desperation"
    PRIMARY KEY(panel_id, character_id)
);
```

### 4.4 Prompts

```sql
-- Reusable prompt fragments
CREATE TABLE prompt_templates (
    id              INTEGER     PRIMARY KEY,
    project_id      INTEGER     REFERENCES creation_projects(id) ON DELETE CASCADE,
    -- NULL project_id = global template, usable in any project
    name            TEXT        NOT NULL,
    category        TEXT        NOT NULL,
    -- category: 'quality' | 'style' | 'character' | 'scene' | 'camera'
    --           | 'lighting' | 'background' | 'effect' | 'negative'
    positive_text   TEXT        NOT NULL DEFAULT '',
    negative_text   TEXT        NOT NULL DEFAULT '',
    variables_json  TEXT        NOT NULL DEFAULT '[]',
    -- variables_json: [{"name":"emotion","description":"character emotion","default":"neutral"}]
    token_count     INTEGER,
    is_global       INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Final assembled prompts for a specific panel (the thing sent to ComfyUI)
CREATE TABLE panel_prompts (
    id                  INTEGER     PRIMARY KEY,
    panel_id            INTEGER     NOT NULL REFERENCES project_panels(id) ON DELETE CASCADE,
    positive_prompt     TEXT        NOT NULL,
    negative_prompt     TEXT        NOT NULL DEFAULT '',
    model_family        TEXT        NOT NULL DEFAULT 'flux',
    -- model_family: 'flux' | 'sdxl' | 'sd15'
    token_count         INTEGER,
    assembly_log_json   TEXT,
    -- assembly_log_json: records which templates and characters contributed which tokens
    -- [{"source":"style_profile","tokens":45},{"source":"character_id:1","tokens":62}]
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_panel_prompts_panel ON panel_prompts(panel_id);
```

### 4.5 Styles

```sql
CREATE TABLE style_profiles (
    id                      INTEGER     PRIMARY KEY,
    project_id              INTEGER     REFERENCES creation_projects(id) ON DELETE CASCADE,
    name                    TEXT        NOT NULL,
    description             TEXT,

    -- Art direction
    art_style               TEXT        NOT NULL DEFAULT 'manhwa_color',
    -- 'manhwa_color' | 'manga_bw' | 'manga_color' | 'webtoon_clean' | 'american_comic' | custom
    line_weight             TEXT        NOT NULL DEFAULT 'medium',
    -- 'hairline' | 'fine' | 'medium' | 'bold' | 'variable'
    coloring_style          TEXT        NOT NULL DEFAULT 'cel_shaded',
    -- 'flat' | 'cel_shaded' | 'painterly' | 'watercolor' | 'monochrome' | 'sketch'
    color_palette_json      TEXT,
    -- [{"role":"primary","hex":"#1a1a2e"},{"role":"accent","hex":"#e94560"}]
    lighting_default        TEXT        NOT NULL DEFAULT 'dramatic',
    -- 'soft' | 'dramatic' | 'backlit' | 'flat' | 'neon' | 'natural'
    background_style        TEXT        NOT NULL DEFAULT 'detailed',
    -- 'simple' | 'detailed' | 'photorealistic' | 'abstract' | 'toned'

    -- Prompt fragments derived from art direction settings
    style_prompt_fragment   TEXT        NOT NULL DEFAULT '',
    -- e.g., "manhwa style, clean linework, vibrant cel shading, Korean webtoon aesthetic"
    quality_prompt_fragment TEXT        NOT NULL DEFAULT '',
    -- e.g., "best quality, masterpiece, highly detailed, sharp focus, 8k"
    style_negative_fragment TEXT        NOT NULL DEFAULT '',
    -- e.g., "blurry, low quality, jpeg artifacts, watermark, signature, text"

    -- Model configuration
    model_family            TEXT        NOT NULL DEFAULT 'flux',
    target_width            INTEGER     NOT NULL DEFAULT 768,
    target_height           INTEGER     NOT NULL DEFAULT 1344,
    -- Webtoon panels: ~768×1344 (9:16). Splash panels: 1344×768 (16:9).

    -- LoRA
    style_lora_path         TEXT,
    style_lora_weight       REAL        NOT NULL DEFAULT 0.7,
    style_trigger_words     TEXT        NOT NULL DEFAULT '',

    created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 4.6 ComfyUI Workflows

```sql
CREATE TABLE comfyui_workflows (
    id                  INTEGER     PRIMARY KEY,
    project_id          INTEGER     REFERENCES creation_projects(id) ON DELETE CASCADE,
    name                TEXT        NOT NULL,
    description         TEXT,
    workflow_type       TEXT        NOT NULL,
    -- workflow_type: 'txt2img' | 'img2img' | 'inpainting' | 'controlnet_pose'
    --               | 'controlnet_depth' | 'controlnet_canny' | 'upscale' | 'ip_adapter'
    model_family        TEXT        NOT NULL DEFAULT 'flux',
    workflow_json       TEXT        NOT NULL,
    -- The complete ComfyUI workflow API JSON (the format from /prompt endpoint)
    parameter_map_json  TEXT        NOT NULL DEFAULT '{}',
    -- Maps panel fields → ComfyUI node inputs:
    -- {"positive_prompt": {"node_id": "6", "input": "text"},
    --  "negative_prompt": {"node_id": "7", "input": "text"},
    --  "seed":            {"node_id": "3", "input": "seed"},
    --  "steps":           {"node_id": "3", "input": "steps"},
    --  "cfg":             {"node_id": "3", "input": "cfg"},
    --  "width":           {"node_id": "5", "input": "width"},
    --  "height":          {"node_id": "5", "input": "height"}}
    default_steps       INTEGER     NOT NULL DEFAULT 28,
    default_cfg         REAL        NOT NULL DEFAULT 1.0,
    -- Flux uses CFG=1.0 (guidance disabled); SDXL typically 7.0
    default_sampler     TEXT        NOT NULL DEFAULT 'euler',
    default_scheduler   TEXT        NOT NULL DEFAULT 'simple',
    supports_lora       INTEGER     NOT NULL DEFAULT 1,
    supports_controlnet INTEGER     NOT NULL DEFAULT 0,
    is_global           INTEGER     NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Individual generation jobs (one per panel generation attempt)
CREATE TABLE generation_jobs (
    id                          INTEGER     PRIMARY KEY,
    project_id                  INTEGER     NOT NULL REFERENCES creation_projects(id) ON DELETE CASCADE,
    panel_id                    INTEGER     NOT NULL REFERENCES project_panels(id) ON DELETE CASCADE,
    workflow_id                 INTEGER     NOT NULL REFERENCES comfyui_workflows(id),
    prompt_id                   INTEGER     REFERENCES panel_prompts(id),

    -- ComfyUI state
    comfyui_client_id           TEXT,
    -- UUID sent to ComfyUI so we can correlate WebSocket messages
    comfyui_prompt_id           TEXT UNIQUE,
    -- The prompt_id returned by ComfyUI's POST /prompt
    status                      TEXT        NOT NULL DEFAULT 'queued',
    -- 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
    progress_pct                REAL        NOT NULL DEFAULT 0.0,
    -- Derived from ComfyUI's 'progress' WebSocket messages

    -- Generation parameters (snapshot at time of submission)
    positive_prompt             TEXT        NOT NULL,
    negative_prompt             TEXT        NOT NULL DEFAULT '',
    width                       INTEGER     NOT NULL DEFAULT 768,
    height                      INTEGER     NOT NULL DEFAULT 1344,
    steps                       INTEGER     NOT NULL DEFAULT 28,
    cfg                         REAL        NOT NULL DEFAULT 1.0,
    seed                        INTEGER,
    -- NULL = random; ComfyUI assigns; stored in output_asset after completion

    -- LoRA overrides for this job (JSON array of {path, weight})
    lora_config_json            TEXT        NOT NULL DEFAULT '[]',

    -- ControlNet input (if workflow supports it)
    controlnet_input_asset_id   INTEGER,
    -- FK to generated_assets; user-uploaded pose/depth reference

    -- Output
    output_asset_id             INTEGER,    -- set on completion; not a FK (circular avoidance)
    final_seed                  INTEGER,    -- actual seed used, reported by ComfyUI

    error_message               TEXT,
    started_at                  TIMESTAMPTZ,
    finished_at                 TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_generation_jobs_panel ON generation_jobs(panel_id);
CREATE INDEX idx_generation_jobs_status ON generation_jobs(project_id, status);
```

### 4.7 Assets

```sql
CREATE TABLE generated_assets (
    id                  INTEGER     PRIMARY KEY,
    project_id          INTEGER     NOT NULL REFERENCES creation_projects(id) ON DELETE CASCADE,
    asset_type          TEXT        NOT NULL,
    -- 'panel' | 'character_ref' | 'expression' | 'expression_sheet'
    -- | 'background' | 'prop' | 'texture' | 'controlnet_input' | 'reference_upload'
    file_path           TEXT        NOT NULL,
    thumbnail_path      TEXT,
    width               INTEGER,
    height              INTEGER,
    file_size_bytes     INTEGER,
    generation_job_id   INTEGER     REFERENCES generation_jobs(id) ON DELETE SET NULL,
    -- NULL if user-uploaded
    is_user_uploaded    INTEGER     NOT NULL DEFAULT 0,
    is_favorite         INTEGER     NOT NULL DEFAULT 0,
    approval_status     TEXT        NOT NULL DEFAULT 'unreviewed',
    -- 'unreviewed' | 'approved' | 'rejected'
    rejection_reason    TEXT,
    tags_json           TEXT        NOT NULL DEFAULT '[]',
    -- Freeform tags: ["background", "city", "night", "establishing"]
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_generated_assets_project ON generated_assets(project_id, asset_type);
CREATE INDEX idx_generated_assets_favorites ON generated_assets(project_id, is_favorite)
    WHERE is_favorite = 1;

-- Export history
CREATE TABLE project_exports (
    id                  INTEGER     PRIMARY KEY,
    project_id          INTEGER     NOT NULL REFERENCES creation_projects(id) ON DELETE CASCADE,
    format              TEXT        NOT NULL DEFAULT 'cbz',
    -- 'cbz' | 'pdf' | 'folder'
    chapter_start       INTEGER,
    chapter_end         INTEGER,
    -- NULL = all chapters
    output_path         TEXT,
    series_id           INTEGER     REFERENCES series(id) ON DELETE SET NULL,
    status              TEXT        NOT NULL DEFAULT 'queued',
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at         TIMESTAMPTZ
);
```

---

## 5. Component Architectures

### 5.1 Story Generator

The Story Generator is a hierarchical AI writing assistant. It works top-down:
premise → arcs → chapters → scenes → panel stage directions.

At every level, the user can write the content themselves or request AI generation.
AI generation is always a draft that the user approves, edits, or rejects.

#### Levels of the hierarchy

```
Project
└─ story_arcs (3–7 for a typical series)
   └─ project_chapters (3–20 per arc)
      └─ project_scenes (2–8 per chapter)
         └─ project_panels (5–30 per scene)
```

#### AI generation at each level

| Level | Prompt to LLM | Output |
|-------|--------------|--------|
| Arc breakdown | "Given this premise and genre, generate a 3-act story arc outline" | 3–7 `story_arcs` rows |
| Chapter outline | "Expand arc synopsis into N chapter outlines with titles and 2-sentence descriptions" | N `project_chapters` rows |
| Scene breakdown | "Break this chapter outline into 4–6 distinct scenes with setting and mood" | `project_scenes` rows |
| Panel directions | "Convert this scene description into 6–12 panel stage directions, one sentence each" | `project_panels.stage_direction` values |
| Dialogue draft | "Write naturalistic dialogue for: [stage direction] [character list]" | `project_panels.dialogue_text` |

#### Models used

- Arc/chapter generation: `default_writer` (narrative quality matters more than speed)
- Scene/panel directions: `default_writer` with shorter context
- Dialogue: `default_reasoner` (better at character voice differentiation)

#### Script editor UI (frontend)

Two views:
- **Outline view**: Expandable tree — project → arcs → chapters → scenes. Each
  node shows a summary line and a generation/edit button.
- **Panel script view**: A chapter in screenwriting format. Each panel is a card
  with stage direction, camera, dialogue, and character assignments side-by-side.

The script editor is a standalone feature within `features/create/`. It does not
require the storyboard or generation systems — a user could write and export
scripts with no image generation.

---

### 5.2 Character Creator

Two data layers per character, always kept in sync:

**Narrative layer** — for story generation context:
- Name, role, age, personality, backstory
- Fed to the LLM when generating dialogue involving this character
- Imported to reading library's `characters` table on export

**Visual layer** — for image generation:
- `appearance_description`: prose description for humans and for the LLM
  to auto-generate a prompt template from
- `prompt_template`: booru-style or natural-language tokens optimized for the
  target model family. This is what goes into prompts.
- `expression_library`: pre-generated face variants (see below)
- `lora_path`: optional LoRA weight file for visual consistency

#### Three paths to create a character

**Path 1: From scratch**
1. User fills in name, role, and appearance description in prose.
2. User clicks "Generate prompt template" → LLM converts prose to image-gen format.
3. User clicks "Generate reference image" → sends to generation pipeline.
4. User edits prompt template based on what the reference image reveals.
5. User generates expression library (one generation per expression, or a contact
   sheet grid in a single generation using the 'expression_sheet' workflow).

**Path 2: Import from Reading Library**
1. User browses their `characters` table from analyzed series.
2. Selects a character → appearance description is pre-filled from the knowledge graph.
3. LLM auto-generates a prompt template from the description.
4. `source_character_id` is stored for traceability.

**Path 3: From reference image (Phase 6)**
1. User uploads a reference image.
2. Vision model generates an appearance description from the image.
3. LLM converts description to prompt template.
4. Optional: LoRA training queued (requires training pipeline, Phase 6).

#### Expression library

A character has a pre-generated expression library: reference face images for
each of the 12 standard expressions plus any custom ones. When a panel is composed,
the user picks an expression from a thumbnail grid for each character in the panel.
That expression's `prompt_modifier` is appended to the character's base prompt.

The expression library is generated with a fixed workflow:
- Character base prompt + expression modifier
- Same seed prefix per character (for consistency within the library, not across panels)
- Square aspect ratio (for face close-ups)

---

### 5.3 Prompt Manager

The Prompt Manager is the assembly engine that converts panel data into a
ComfyUI-ready prompt string.

#### Assembly order (all model families)

```
assembled_positive =
  style_profile.quality_prompt_fragment          (e.g., "best quality, masterpiece")
  + style_profile.style_prompt_fragment          (e.g., "manhwa style, clean linework")
  + style_profile.style_trigger_words            (LoRA trigger words)
  + [for each character in panel_characters:]
      character.prompt_template
      + expression.prompt_modifier               (e.g., "smiling, eyes closed")
      + panel_character.action_note              (e.g., "reaching forward")
  + camera_angle_to_text(panel.camera_angle)     (e.g., "medium shot, from below")
  + scene.lighting_notes                         (e.g., "dramatic rim lighting, blue tones")
  + panel.foreground_notes
  + panel.background_notes
  + scene.setting_description
```

#### Model-family differences

| Aspect | Flux | SDXL | SD 1.5 |
|--------|------|------|--------|
| Negative prompt | Not used (omit) | Used | Used |
| Language style | Natural language prose | Mixed (booru tags preferred) | Booru tags |
| Token limit | No hard limit (T5 encoder) | 77 tokens per encoder (2 encoders) | 77 tokens |
| CFG scale | 1.0 (fixed) | 5.0–9.0 | 7.0 |
| Quality tags | Less important | Important | Critical |

The `model_family` field on `panel_prompts` records which rules were applied.
Switching the project's model family triggers a prompt regeneration offer.

#### Token budget management

For SDXL: the positive prompt is limited to 154 tokens (77 × 2 encoders). If the
assembled prompt exceeds this, the Prompt Manager:
1. Shows a token count badge (red when over budget)
2. Identifies which layer is largest
3. Offers a "compress" action (LLM summarizes the over-budget section)

For Flux: no hard limit, but prompts over ~300 tokens show diminishing returns.
The UI shows the count but does not enforce a hard cap.

#### Prompt template library

Beyond the automatic assembly, users can save named templates for:
- Recurring scene types ("Training montage panel", "City establishing shot")
- Recurring moods ("Rainy introspection", "Battle climax")
- Recurring environments ("Dungeon corridor", "Modern Seoul street")

Templates are stored in `prompt_templates` with `is_global = 1` to share
across projects.

---

### 5.4 Scene Planner

The Scene Planner is the bridge between script and generation. It answers the
question: "Given what I wrote, what exactly goes in each panel?"

#### Two views

**Script view**: A chapter rendered as a column of panel cards. Each card shows
the stage direction, camera angle, character assignments, and generation status
badge. Users write the script here.

**Storyboard view**: A visual grid of panel thumbnails (or placeholder boxes if
not generated). Panels are drag-and-droppable to reorder. Clicking a panel opens
the script + generation side panel. This is the "at a glance" view of a chapter.

#### Panel layout system

**Webtoon format**: Fixed width, variable height panels stacked vertically.
No page concept — the chapter is one continuous scroll.
Panel types: `standard` (square/landscape), `tall` (portrait), `wide` (full-width),
`inset` (small panel overlapping a larger one).

**Manga format**: Fixed-size pages (A4/B5). Each page has a grid.
The 12-column grid allows: 1-panel, 2-panel (6+6), 3-panel (4+4+4),
4-panel (6+6 top, 6+6 bottom), 2+1 (6+6 top, 12 bottom), etc.
`layout_json` stores the grid coordinates: `{"x":0,"y":0,"w":6,"h":8}`.

#### Camera angle vocabulary

| Code | Image gen equivalent | Usage |
|------|---------------------|-------|
| `extreme_close_up` | "extreme close-up, face only, eyes filling frame" | Emotion emphasis |
| `close_up` | "close-up shot, face and shoulders" | Dialogue, reaction |
| `medium` | "medium shot, waist up" | Standard dialogue, action |
| `wide` | "wide shot, full body, environment visible" | Action, context |
| `extreme_wide` | "establishing shot, tiny figures in large environment" | World-building |
| `overhead` | "bird's eye view, top-down angle" | Geography, powerlessness |
| `worm_eye` | "low angle shot, looking up, dramatic" | Power, intimidation |
| `dutch_angle` | "dutch angle, tilted, 30-degree camera roll" | Tension, unease |

The camera angle is converted to its image-gen text by the Prompt Manager at
assembly time. The user selects the code name; they never type the prompt text.

#### Transition design

Panel-to-panel transitions are stored (`transition_from_prev`) using McCloud's
six transition types. This data is currently annotation only but will later inform:
- Pacing analysis (too many moment-to-moment = slow chapter)
- AI-assisted script review ("this scene has 8 action-to-action panels in a row,
  consider varying the transitions")

---

### 5.5 Style Manager

A style profile captures everything that makes a series look visually unified.
One project has exactly one active style profile, but the user can create several
and switch during development (useful for trying different art directions).

#### Art direction settings → prompt fragment generation

When the user changes art direction settings (art style, coloring, line weight),
the Style Manager auto-generates `style_prompt_fragment` using the LLM:

> "Given these art style settings: [art_style=manhwa_color, coloring=cel_shaded,
> line_weight=medium, lighting=dramatic], write an image generation prompt
> fragment (15–25 words) that captures this visual style."

The user can edit the generated fragment. The generation is a starting point.

#### LoRA stack management

A panel's final generation uses up to three LoRAs stacked:
1. **Style LoRA** (from `style_profiles.style_lora_path`) — applies the series art style
2. **Character LoRA(s)** (from `project_characters.lora_path`) — one per character in the panel
3. Model-specific LoRA (e.g., detail enhancement, resolution improvement) — optional

The LoRA stack is serialized into `generation_jobs.lora_config_json`:
```json
[
  {"path": "models/loras/my_style.safetensors", "weight": 0.7},
  {"path": "models/loras/char_jinwoo.safetensors", "weight": 0.85},
  {"path": "models/loras/char_chahaein.safetensors", "weight": 0.8}
]
```

**LoRA weight collision**: When two character LoRAs are stacked, total LoRA
influence can exceed 1.0 and cause visual artifacts. The Style Manager warns
when the sum of character LoRA weights in a panel exceeds 1.6. Recommended
mitigation: reduce individual weights proportionally.

#### Color palette guidance

The `color_palette_json` field stores the project's color palette. Future use:
- Feed as ControlNet color guidance (a color block image)
- Include in style prompt ("color palette: deep navy, crimson red, silver white")
- Palette validation: alert if a generated panel's dominant colors deviate
  significantly from the palette (computed via PIL color histogram comparison)

#### Per-format defaults

| Format | Default resolution | Style notes |
|--------|-------------------|-------------|
| `manhwa_color` | 800×1200 | Color, clean linework, modern Korean style |
| `manga_bw` | 1200×1700 | Grayscale, screentone, traditional Japanese |
| `webtoon_clean` | 800×1344 | Flat colors, minimal line variation, web-optimized |
| `american_comic` | 1024×1568 | Bold outlines, dynamic color, American superhero |

---

### 5.6 ComfyUI Integration

ComfyUI runs as a separate process alongside the backend. The backend communicates
with it via ComfyUI's HTTP + WebSocket API.

#### ComfyUI API surfaces used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/prompt` | POST | Submit a workflow for generation |
| `/queue` | GET | Check queue depth and running jobs |
| `/history/{prompt_id}` | GET | Get completed job output paths |
| `/view` | GET | Download a generated image by filename |
| `/system_stats` | GET | GPU VRAM usage, model loaded |
| `/ws` | WebSocket | Real-time progress events |

ComfyUI's WebSocket sends:
```json
{ "type": "progress", "data": { "value": 14, "max": 28 } }
{ "type": "executed",  "data": { "prompt_id": "abc...", "output": { "images": [{"filename":"...","subfolder":"","type":"output"}] } } }
```

#### Job submission flow

```
1. User clicks "Generate" on a panel
2. Backend builds generation_jobs row (status='queued')
3. Backend reads workflow_json from comfyui_workflows
4. Backend applies parameter_map_json to inject:
     - positive_prompt
     - negative_prompt (omitted for Flux workflows)
     - width, height
     - steps, cfg, seed
     - LoRA node config (path + weight per LoRA)
     - ControlNet input image (if applicable)
5. Backend generates a random client_id (UUID)
6. Backend POSTs {"prompt": <workflow>, "client_id": <uuid>} to ComfyUI /prompt
7. ComfyUI returns {"prompt_id": "abc..."}
8. Backend stores comfyui_prompt_id in generation_jobs
9. Backend opens WebSocket connection to ComfyUI /ws (or reuses shared connection)
10. On progress events: update generation_jobs.progress_pct
11. On 'executed' event: download image from /view, save to generated_assets
12. Update generation_jobs.status='completed', output_asset_id=<new asset id>
13. Update project_panels.generation_status='generated', final_asset_id=<asset id>
14. Broadcast 'panel_generated' notification via AIStudio WebSocket (/ws/notifications)
```

#### ComfyUI connection management

One persistent WebSocket connection from the AIStudio backend to ComfyUI.
All generation job progress is routed through this single connection using
`client_id` matching (ComfyUI sends messages tagged with the `client_id`).

The connection is maintained in `services/comfyui_service.py` as a singleton,
reconnecting automatically with exponential backoff if dropped.

#### Workflow template design

Workflows are stored as the complete ComfyUI API JSON (not the GUI-format node
graph). This is the format from ComfyUI's `/prompt` endpoint. The GUI-format
workflows require conversion; the API-format works directly.

The `parameter_map_json` maps symbolic names to node inputs:
```json
{
  "positive_prompt":  { "node_id": "6",  "input": "text" },
  "negative_prompt":  { "node_id": "7",  "input": "text" },
  "seed":             { "node_id": "3",  "input": "seed" },
  "steps":            { "node_id": "3",  "input": "steps" },
  "cfg":              { "node_id": "3",  "input": "cfg" },
  "width":            { "node_id": "5",  "input": "width" },
  "height":           { "node_id": "5",  "input": "height" },
  "lora_1_path":      { "node_id": "15", "input": "lora_name" },
  "lora_1_weight":    { "node_id": "15", "input": "strength_model" },
  "controlnet_image": { "node_id": "20", "input": "image" }
}
```

#### Bundled workflow templates

AIStudio ships with these starter templates (stored as JSON files, imported on
first run):

| Name | Type | Model family | Description |
|------|------|-------------|-------------|
| Flux Standard | txt2img | Flux | Basic Flux.1-dev generation |
| Flux Fast | txt2img | Flux | Flux.1-schnell, 8-step iteration |
| Flux + Character LoRA | txt2img | Flux | Flux with up to 2 character LoRAs |
| Flux + ControlNet Pose | controlnet_pose | Flux | Flux with OpenPose skeleton control |
| Flux + IP-Adapter | ip_adapter | Flux | Character reference image consistency |
| SDXL Standard | txt2img | SDXL | Basic SDXL generation |
| SDXL + LoRA Stack | txt2img | SDXL | SDXL with style + character LoRAs |
| Upscale 4x | upscale | any | 4× upscale of completed panel |
| Inpaint Panel | inpainting | Flux | Fix a specific region of a generated panel |

---

### 5.7 Flux Integration

Flux (Black Forest Labs) is the primary target model family. Understanding its
architecture differences prevents wasted prompting effort.

#### Architecture differences from SDXL

| Property | Flux | SDXL |
|----------|------|------|
| Text encoders | T5-XXL + CLIP-L | CLIP-L + CLIP-G |
| Negative prompts | Effectively non-functional | Core to quality |
| Token limit | ~300 tokens (T5 handles long text) | 77 tokens per encoder |
| Language understanding | Excellent with natural language | Better with booru tags |
| CFG guidance scale | 1.0 (disable guidance) | 6.0–9.0 |
| Optimal steps | 20–30 (Dev) / 4–8 (Schnell) | 25–40 |
| Conditioning | Rectified flow | Latent diffusion |

**The negative prompt implication**: Flux workflows have no negative conditioning
node. The `negative_prompt` field on `panel_prompts` and `generation_jobs` is
stored but not sent when `model_family = 'flux'`. The `parameter_map_json` simply
omits the `negative_prompt` key for Flux workflows.

**The language style implication**: Flux works better with natural language
descriptions ("a tall young man with black hair standing in front of a glowing
gate, dramatic lighting, cinematic framing") than booru tag lists. The Style
Manager auto-generates prose-style `style_prompt_fragment` for Flux and
tag-style for SDXL.

#### Flux model variants

| Variant | Steps | VRAM | Use case |
|---------|-------|------|---------|
| `flux1-dev` | 20–30 | 24 GB (fp16) / 12 GB (fp8) | Final quality generation |
| `flux1-schnell` | 4–8 | 24 GB (fp16) / 12 GB (fp8) | Rapid iteration, composition checks |
| `flux1-dev-Q4` | 20–30 | 8 GB | Low VRAM devices; lower quality |

The workflow template stores the model checkpoint filename. The Style Manager's
"model configuration" section lets the user point to their local Flux checkpoint.

#### Flux ControlNet for composition

Flux-ControlNet (community implementations, e.g., jasperai/Flux.1-dev-Controlnet-*)
accepts:
- **OpenPose skeleton**: Controls character poses and positions
- **Depth map**: Controls scene depth and spatial arrangement
- **Canny edges**: Controls linework structure

The ControlNet input (`controlnet_input_asset_id`) references a `generated_assets`
row of type `controlnet_input`. Users can:
1. Upload a hand-drawn pose sketch
2. Use a reference photo (local file upload)
3. Generate a pose skeleton with a pose library (future)

#### IP-Adapter for character consistency

Flux IP-Adapter (when models become stable) allows passing a reference image
alongside the text prompt, with the model maintaining visual identity from the
reference. This is the most promising path to character consistency without LoRA
training.

IP-Adapter input: the character's approved `cover_asset_id` image.
IP-Adapter strength: configurable (0.3–0.9). Higher values = more faithful to
reference but less responsive to prompt.

For now (Phase 5): LoRA is the primary consistency mechanism. IP-Adapter is
designed into the schema but its workflow template ships when the community
models stabilize.

---

### 5.8 Asset Library

The Asset Library is the media browser for all generated and uploaded content
within a project. It is not a file manager — it is a structured, searchable,
approval-workflow-driven asset catalog.

#### Asset hierarchy (conceptual)

```
Project
├─ Panels/                  — generated panel images (the primary output)
├─ Characters/
│  ├─ {CharacterName}/
│  │  ├─ Reference images   — approved look references
│  │  └─ Expressions/       — expression library images
├─ Backgrounds/             — standalone background assets for reuse
├─ Props/                   — standalone prop assets
├─ ControlNet Inputs/       — pose/depth reference images (user uploads)
└─ Reference Uploads/       — mood board references (user uploads)
```

#### Asset operations

**Approve**: Sets `approval_status = 'approved'` and links the asset as the
panel's `final_asset_id`. Only one asset per panel can be approved.

**Reject**: Sets `approval_status = 'rejected'`, stores `rejection_reason`.
Rejected assets remain in the library for comparison — they are never deleted
automatically.

**Regenerate**: Queues a new `generation_jobs` row with the same `panel_id`,
copying the prompt from the previous job (but with `seed = NULL` for a new random
result). Increments an internal version count (derived from `COUNT(generation_jobs
WHERE panel_id = X)`).

**Upscale**: Creates a new generation job with the `upscale` workflow type,
using the current asset as the input image. Output is a new `generated_assets` row.

**Edit in inpainting**: Creates a generation job with `inpainting` workflow,
using the current asset as the base. The user selects the region to regenerate
in the frontend (mask drawn over the thumbnail).

**Favorite**: Sets `is_favorite = 1`. Favorited assets appear in a quick-access
gallery for reuse in other panels (backgrounds, props).

**Reuse as background**: Favorited background assets appear in the Scene Planner's
background picker, so the same background can be assigned to multiple panels in a
scene without regenerating.

#### Version history

All generation attempts for a panel are kept (no auto-deletion). The Asset Library
shows them as a filmstrip below the current approved asset. The user can
"approve" any historical version, making it the final asset.

#### File organization on disk

```
generated/
  {project_id}/
    panels/
      {panel_id}/
        v001_{seed}.png
        v002_{seed}.png
        v003_{seed}.png      ← currently approved
    characters/
      {character_id}/
        ref_001.png
        expr_happy.png
        expr_angry.png
    backgrounds/
      bg_{scene_id}_001.png
    controlnet/
      pose_{panel_id}.png
```

Files use `{seed}` in the name so the user can reproduce any result outside AIStudio.

---

### 5.9 Project Management

The Project Manager is the top-level view of a creation project. It answers:
"What have I made, what is in progress, and what is left to do?"

#### Chapter kanban

A horizontal kanban board. Each column is a chapter status:

```
Draft → Scripted → Storyboarded → Generating → Generated → Approved → Exported
```

Chapter cards show: chapter number, title, panel count, generation progress
(`approved_panels / total_panels`). Clicking a card opens that chapter in the
Scene Planner / Storyboard view.

#### Project dashboard statistics

```
Total panels: 247
Scripted:    232  (94%)
Generated:   180  (73%)
Approved:    141  (57%)
────────────────────────
Generation queue: 0 jobs running, 3 queued
VRAM status: ComfyUI active, 18 GB / 24 GB used
Last export: Chapter 1–8, CBZ, 2024-02-15
```

#### Export pipeline

```
1. User selects: format (CBZ/PDF/folder), chapter range, destination library
2. Backend validates: all panels in range have approved assets
3. If validation fails: export blocked; shows list of missing panels
4. Backend creates project_exports row (status='queued')
5. Background worker:
   a. For each chapter in range, in order:
      - For each panel in order (sequence_order):
        - Fetch final_asset_id → get file_path from generated_assets
        - Optionally composite dialogue text overlay onto image (if enabled)
        - Add to output (ZIP entry for CBZ, page for PDF, file for folder)
   b. Write output to exports/{project_id}/export_{timestamp}.cbz
   c. Update project_exports.output_path, status='completed'
6. If format=CBZ and destination_library_id is set:
   a. Run the library scanner on the output file path
   b. Scanner creates/updates the series in the reading library
   c. Sets series.is_created = 1
   d. Sets creation_projects.series_id = newly_created_series.id
7. Broadcast 'export_complete' notification
```

#### Library integration

After the first export:
- `creation_projects.series_id` is set
- `series.is_created = 1` marks it as a created (not imported) series
- The Library page shows a "Created" badge on the series card
- Subsequent exports add chapters to the existing series (the scanner handles
  new CBZ detection if chapter numbers increment correctly)

The reading experience is identical to any other series. The creator reads
their own work in the same reader, with the same keyboard shortcuts, the same
bookmark system, and the same "Continue Reading" flow.

---

## 6. The Consistency System

Visual consistency — making Character A look like the same person across panel 1
and panel 847 — is the hardest unsolved problem in AI-generated sequential art.
The architecture uses a layered approach, from easiest to most powerful:

### Layer 1: Canonical Prompt Template (always active)

Every character has a meticulously crafted `prompt_template` that is always
included in full when that character appears. Precise descriptors (hair color,
eye color, distinctive features, clothing) anchor the model's generation.

**Reliability**: Medium. Same prompt → similar results, but seed variation
causes drift. Best for background characters and characters with highly
distinctive features.

**Cost**: Zero. No additional infrastructure.

### Layer 2: Expression Library Reference (workflow-assisted)

Before starting a chapter, the user generates the character's expression library
using a consistent seed prefix. These reference images document what the character
should look like in each emotion. When a generated panel looks wrong, the user
compares against the expression library to decide whether to regenerate.

**Reliability**: Medium. The reference images are aspirational, not causal —
the model doesn't "see" them automatically.

**Cost**: Generation time for the expression library (one-time per character).

### Layer 3: Character LoRA (most reliable, most work)

A LoRA fine-tuned on 10–30 reference images of the character. The LoRA learns the
character's face, body proportions, and clothing at the weight level, making the
character appear consistently regardless of prompt phrasing or seed.

**Reliability**: High (for faces and key visual elements).

**Cost**: LoRA training (30–90 minutes on a modern GPU). Requires a training
pipeline (Phase 5, using Kohya SS or similar). The LoRA path is stored in
`project_characters.lora_path`.

### Layer 4: IP-Adapter (reference-based, no training)

Flux IP-Adapter takes a reference image and conditions generation on it
alongside the text prompt. No training required — the reference image is passed
at inference time.

**Reliability**: Medium-high for facial features. Less reliable for clothing details.

**Cost**: One inference call per panel (same cost as normal generation).
Requires IP-Adapter model files and a compatible workflow.

**Phase plan**: Layer 4 support is designed into the schema but not implemented
until community IP-Adapter models for Flux stabilize. The `controlnet_input_asset_id`
field serves as the IP-Adapter input reference until a dedicated field is added.

### Practical recommendation

For Phase 5 launch:
- **Primary characters** (appear in >20% of panels): train a character LoRA.
- **Secondary characters** (5–20% of panels): use precise prompt template +
  expression library. Optionally train a LoRA if quality matters.
- **Incidental characters** (<5% of panels): prompt template only.

The Character Creator UI reflects this by showing a "Consistency Level" indicator:
- 🔴 Template only
- 🟡 Template + Expression Library
- 🟢 Template + Expression Library + LoRA

---

## 7. AI Assistance in Creation Studio

Creation Studio uses the same Ollama infrastructure as the Reading AI pipeline.
Generation and analysis jobs share the Ollama lock, so they serialize correctly.

### LLM tasks (text generation)

| Task | Model | Endpoint |
|------|-------|---------|
| Story arc generation | `default_writer` | `POST /ai/create/story/arcs` |
| Chapter outline | `default_writer` | `POST /ai/create/story/chapters` |
| Scene breakdown | `default_writer` | `POST /ai/create/story/scenes` |
| Panel directions | `default_writer` | `POST /ai/create/story/panels` |
| Dialogue generation | `default_reasoner` | `POST /ai/create/story/dialogue` |
| Prompt template generation | `default_writer` | `POST /ai/create/characters/{id}/generate-prompt` |
| Script review / pacing analysis | `default_reasoner` | `POST /ai/create/chapters/{id}/review` |

### Vision tasks (image understanding)

| Task | Model | Purpose |
|------|-------|---------|
| Appearance description from reference | `ocr_model` (vision) | Path 3 character creation |
| Panel quality check | `ocr_model` (vision) | "Does this panel match the stage direction?" |

### Reading Library knowledge as creative input

The most powerful feature of building Creation Studio inside AIStudio rather than
as a separate tool: the user's reading library is a creative resource.

- **Character import**: Import characters from analyzed series directly into a project.
  Their AI-extracted descriptions become starting points for visual design.
- **Style reference**: Point the Style Manager at a series in the library; the LLM
  analyzes its OCR metadata and AI summaries to generate a matching style prompt.
- **Trope library** (future): "Find me 5 examples from my library of establishing
  shots of dungeons" → semantic search returns panels matching the query.
- **Plot inspiration** (future): "What are common character arc patterns in series
  similar to my project?" → knowledge graph analysis across the library.

---

## 8. Phase Plan for Creation Studio

### Phase 5 — Core Creation Studio

**Project Management**
- Project CRUD, chapter kanban, status tracking, export to CBZ

**Story Generator**
- Hierarchical script editor (arcs → chapters → scenes → panels)
- AI assistance at each level via `default_writer`
- Script view and storyboard view

**Character Creator**
- Paths 1 and 2 (from scratch, import from library)
- Expression library generation
- Prompt template generation from prose description
- LoRA path configuration (no training pipeline — user brings pre-trained LoRAs)

**Style Manager**
- Style profile CRUD
- Auto-generation of style prompt fragment from settings
- LoRA stack configuration

**Prompt Manager**
- Automatic prompt assembly from panel data
- Token budget display
- Template library (global and per-project)
- Model-family-aware assembly (Flux vs. SDXL)

**ComfyUI Integration**
- Bundled workflow templates (txt2img, character LoRA, upscale)
- Job submission, WebSocket progress, asset download
- Panel generation UI

**Flux Integration**
- Flux-specific workflow templates
- No-negative-prompt handling
- Flux ControlNet (pose) if stable models available

**Asset Library**
- Panel version history
- Approve / reject / regenerate workflow
- Upscale action
- Basic file browser by type

### Phase 6 — Creation Studio Advanced

- LoRA training pipeline (Kohya SS integration or built-in)
- IP-Adapter character consistency
- Inpainting panel editor (in-app)
- Dialogue text overlay compositor (for webtoon-style text in panels)
- PDF export with page layout (for manga format)
- Multi-user project sharing (beyond Phase 6 likely)
- Path 3 character creation (from reference image)
- Trope library and style reference from reading library

---

## 9. Frontend Architecture

Creation Studio is `features/create/` in the frontend. It is a large feature that
warrants sub-feature organization:

```
features/create/
├─ api.ts                    All creation studio API calls
├─ hooks.ts                  useQuery / useMutation wrappers
├─ store.ts                  Zustand: active project, active chapter, panel selection
├─ types.ts                  TypeScript types for all creation entities
├─ index.ts                  Public surface
└─ components/
   ├─ ProjectDashboard.tsx    Chapter kanban, statistics, export button
   ├─ StoryEditor.tsx         Arc/chapter/scene outline tree
   ├─ PanelScript.tsx         Panel card list (script view)
   ├─ Storyboard.tsx          Panel thumbnail grid (storyboard view)
   ├─ PanelEditor.tsx         Single panel detail: script + generation
   ├─ CharacterCreator.tsx    Character form, expression library
   ├─ PromptPreview.tsx       Live assembled prompt with token count
   ├─ StyleEditor.tsx         Style profile form
   ├─ AssetBrowser.tsx        Project media library
   ├─ GenerationSidebar.tsx   Queue status, active generation progress
   └─ ExportDialog.tsx        Format/range/destination selection
```

Zustand (`features/create/store.ts`) owns:
- `activeProjectId`
- `activeChapterId`
- `selectedPanelId`
- `storyboardViewMode` ('script' | 'storyboard')
- `assetBrowserOpen`
- `generationSidebarOpen`

TanStack Query owns all project data, characters, panels, assets, and generation
job status (polled every 3 seconds while jobs are active, idle otherwise).

---

## 10. Backend Architecture

```
routes/
├─ create.py              Creation Studio HTTP routes

services/
├─ story_service.py       Script generation, AI assistance
├─ character_service.py   Character CRUD, expression library
├─ prompt_service.py      Prompt assembly, template management
├─ comfyui_service.py     ComfyUI HTTP + WebSocket client (singleton)
├─ generation_service.py  Job queuing, status tracking
├─ asset_service.py       Asset CRUD, file management
└─ export_service.py      CBZ/PDF/folder export, library sync

workers/
└─ generation_worker.py   Polls generation_jobs queue, submits to ComfyUI,
                          downloads results, updates asset records
```

`comfyui_service.py` is a singleton (one instance per server process) that
maintains the persistent WebSocket connection to ComfyUI and routes progress
events to the correct `generation_jobs` row. It is initialized in `create_app()`
alongside the Ollama lock.

---

## 11. Design Review Notes

### Review 1 — data flow completeness

- Every panel's generation is fully auditable: `project_panels` → `panel_prompts`
  → `generation_jobs` → `generated_assets`. No step is implicit.
- The circular FK problem (panels reference assets, assets reference jobs, jobs
  reference panels) is resolved by using plain INTEGER columns (not FK constraints)
  for `final_asset_id` on `project_panels` and `output_asset_id` on `generation_jobs`,
  consistent with the pattern established in DATABASE.md §4.22.
- The `is_user_edited` pattern from the reading AI pipeline carries over: user-written
  stage directions and prompt templates are not overwritten by AI re-generation.

### Review 2 — consistency system completeness

- Three layers (prompt template, expression library, LoRA) cover the full
  spectrum from zero-cost to maximum-quality consistency.
- IP-Adapter is designed into the schema but not implemented until stable.
  No schema changes will be needed when it ships.
- The Character Creator UI surfaces the consistency level clearly so users
  understand the trade-off before starting generation.

### Review 3 — library integration correctness

- `series.is_created = 1` cleanly distinguishes created from imported series
  without schema changes (field already exists in DATABASE.md §4.2).
- The export → scan pipeline reuses the existing `library_service` scan logic
  rather than duplicating it. The exporter writes a valid CBZ/folder; the scanner
  imports it exactly as it would any user-provided file.
- `creation_projects.series_id` is a nullable FK with `ON DELETE SET NULL`, so
  deleting the exported series from the library does not delete the project.
