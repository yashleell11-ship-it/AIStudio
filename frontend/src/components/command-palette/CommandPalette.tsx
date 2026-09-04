"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  BookOpen,
  CornerDownLeft,
  Globe,
  LogOut,
  Search,
  Settings as SettingsIcon,
  Sparkles,
} from "lucide-react";
import { Kbd } from "@/components/ui/kbd";
import { mobileNav, moreNav, primaryNav, secondaryNav } from "@/config/nav";
import { useLogout } from "@/features/auth/hooks";
import { libraryCoverUrl } from "@/features/library/api";
import { useSearch } from "@/features/library/hooks";
// From the modules directly, not the `@/features/preferences` barrel: the
// palette ships in the app shell, and the barrel also re-exports the settings
// panels, which would then be pulled into every page's bundle.
import {
  READING_THEMES,
  READING_THEME_META,
  isReadingTheme,
} from "@/features/preferences/theme";
import { useReadingTheme } from "@/features/preferences/theme-store";
import {
  DESIGN_PRESETS,
  DESIGN_PRESET_META,
  isDesignPreset,
} from "@/features/preferences/presets";
import { useDesignPreset } from "@/features/preferences/preset-store";
import { sourceImageUrl } from "@/features/sources/api";
import { useSources } from "@/features/sources/hooks";
import { useShortcut } from "@/lib/keyboard";
import { cn } from "@/lib/cn";
import {
  groupCommands,
  rankCommands,
  routeCommands,
  type Command,
  type RankedCommand,
} from "./commands";
import { highlightSegments } from "./fuzzy";

/**
 * How long the input must be still before the library is queried. Long enough
 * that typing a title is one request rather than one per keystroke, short enough
 * that it still feels like it is keeping up.
 */
const SEARCH_DEBOUNCE_MS = 220;

/**
 * `GET /library/search` takes `q`, `page` and `per_page` (1–200) and nothing
 * else — backend/routes/library.py:525-533. Eight rows is what fits above the
 * fold beside the routes and actions; asking for more would only be discarded
 * here.
 */
const SERIES_RESULT_LIMIT = 8;

/** The shortest query worth a round trip. One character matches nearly everything. */
const MIN_QUERY_LENGTH = 2;

/**
 * A result row's thumbnail, `size-8`. The palette opens on every `/` keypress
 * and lists eight series, so its covers are the ones most likely to be fetched
 * for nothing — this is the width the cover proxy renders to, not just a
 * `sizes` hint (`lib/cover-url.ts`).
 */
const ROW_IMAGE_SIZES = "32px";

const KIND_ICON = {
  route: ArrowRight,
  series: BookOpen,
  source: Globe,
  action: Sparkles,
} as const;

const ACTION_ICON = {
  "action:settings": SettingsIcon,
  "action:sign-out": LogOut,
} as const;

/** `action:theme:<id>` — one command per palette, so any of the forty is one query away. */
const THEME_ACTION_PREFIX = "action:theme:";

/** `action:preset:<id>` — the shape half of the same idea. */
const PRESET_ACTION_PREFIX = "action:preset:";

/** Title with the matched characters emphasised. */
function Highlighted({ text, indices }: { text: string; indices: readonly number[] }) {
  return (
    <>
      {highlightSegments(text, indices).map((segment, index) =>
        segment.match ? (
          <mark key={index} className="bg-transparent font-semibold text-primary">
            {segment.text}
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </>
  );
}

/**
 * ⌘K / Ctrl+K jump-to-anything.
 *
 * Registered through the app's keyboard registry (`@/lib/keyboard`) rather than
 * with a second `window` listener: it shares the one global handler, shows up in
 * Settings → Shortcuts for free, and inherits the registry's rule that a
 * shortcut does not fire while focus is in a field.
 *
 * This outer component holds nothing but the open flag and the binding, so the
 * palette's queries — the library search and the installed-source list — do not
 * run on pages where nobody presses ⌘K. Everything else lives in
 * `CommandPaletteDialog`, which only mounts while open.
 */
export function CommandPalette() {
  const [open, setOpen] = useState(false);

  useShortcut({
    id: "shell.command-palette",
    keys: "mod+k",
    description: "Open the command palette",
    group: "General",
    handler: useCallback(() => setOpen(true), []),
  });

  if (!open) return null;
  return <CommandPaletteDialog onClose={() => setOpen(false)} />;
}

function CommandPaletteDialog({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const logout = useLogout();
  const { theme, setTheme } = useReadingTheme();
  const { preset, setPreset } = useDesignPreset();

  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [highlighted, setHighlighted] = useState(0);

  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const baseId = useId();
  const listboxId = `${baseId}-listbox`;

  // Debounce only the *server* query. The local commands re-rank on every
  // keystroke because that costs nothing and feels immediate.
  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) return;
    const timer = window.setTimeout(() => setDebouncedQuery(trimmed), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query]);

  const trimmedQuery = query.trim();
  // Derived rather than stored: backing out to one character has to stop the
  // search immediately, and computing it here avoids a second state write (and
  // the render it would cost) on every keystroke. While a longer query settles,
  // the previous answer deliberately stays on screen instead of blanking, and
  // `isSearching` says so.
  const searchQuery = trimmedQuery.length >= MIN_QUERY_LENGTH ? debouncedQuery : "";

  const search = useSearch({ q: searchQuery, per_page: SERIES_RESULT_LIMIT });
  const sources = useSources();

  const runAction = useCallback(
    async (id: string) => {
      if (id.startsWith(THEME_ACTION_PREFIX)) {
        const next = id.slice(THEME_ACTION_PREFIX.length);
        if (isReadingTheme(next)) setTheme(next);
        return;
      }
      if (id.startsWith(PRESET_ACTION_PREFIX)) {
        const next = id.slice(PRESET_ACTION_PREFIX.length);
        if (isDesignPreset(next)) setPreset(next);
        return;
      }
      switch (id) {
        case "action:settings":
          router.push("/settings");
          return;
        case "action:sign-out":
          try {
            await logout.mutateAsync();
          } catch {
            // `useLogout.onSettled` clears the session locally either way.
          }
          router.replace("/login");
          return;
      }
    },
    [logout, router, setTheme, setPreset],
  );

  const commands = useMemo<Command[]>(() => {
    const seriesCommands: Command[] = (search.data?.items ?? []).map((series) => ({
      id: `series:${series.id}`,
      title: series.title,
      subtitle: `${series.chapter_count} chapters`,
      group: "Library",
      kind: "series",
      href: `/library/${series.id}`,
      keywords: [series.source_id],
      imageUrl: libraryCoverUrl(series.cover_url, ROW_IMAGE_SIZES),
    }));

    const sourceCommands: Command[] = (sources.data ?? []).map((source) => ({
      id: `source:${source.id}`,
      title: source.name,
      subtitle: source.description || "Browse this source",
      group: "Sources",
      kind: "source",
      href: `/sources/${encodeURIComponent(source.id)}`,
      keywords: [source.id],
      imageUrl: source.icon_url ? sourceImageUrl(source.icon_url) : null,
    }));

    /*
     * Every palette, individually. Cycling made sense at four themes and is
     * useless at forty: nobody wants to press Enter nineteen times to reach
     * Kanagawa. As commands they are fuzzy-searchable by name, by author and by
     * id, which is how a rice library is meant to be navigated — "gruv", Enter.
     *
     * They sit in their own group, ranked below Actions, so an empty palette
     * still opens on routes rather than on a wall of colour.
     */
    const themeCommands: Command[] = READING_THEMES.map((id) => {
      const meta = READING_THEME_META[id];
      return {
        id: `${THEME_ACTION_PREFIX}${id}`,
        title: id === theme ? `Theme: ${meta.label} (current)` : `Theme: ${meta.label}`,
        subtitle: meta.description,
        group: "Themes",
        kind: "action",
        keywords: ["theme", "appearance", "palette", meta.scheme, id, meta.author ?? ""],
        swatch: { bg: meta.swatch.bg, accent: meta.swatch.accent },
      };
    });

    /*
     * The five presets, on the same terms as the palettes. No swatch: a preset
     * has no colour of its own, which is the point — "flat", Enter, and the
     * app you are looking at reshapes without changing hue.
     */
    const presetCommands: Command[] = DESIGN_PRESETS.map((id) => {
      const meta = DESIGN_PRESET_META[id];
      return {
        id: `${PRESET_ACTION_PREFIX}${id}`,
        title:
          id === preset ? `Design: ${meta.label} (current)` : `Design: ${meta.label}`,
        subtitle: meta.description,
        group: "Design",
        kind: "action",
        keywords: ["design", "preset", "layout", "density", "shape", id],
      };
    });

    const actionCommands: Command[] = [
      {
        id: "action:settings",
        title: "Open settings",
        subtitle: "Appearance, notifications, downloads, shortcuts",
        group: "Actions",
        kind: "action",
        keywords: ["preferences", "options", "configure"],
      },
      {
        id: "action:sign-out",
        title: "Sign out",
        subtitle: "End this session",
        group: "Actions",
        kind: "action",
        keywords: ["logout", "log out", "exit"],
      },
    ];

    return [
      ...seriesCommands,
      ...sourceCommands,
      // `mobileNav` last so its duplicate hrefs lose the de-duplication to the
      // sidebar entries, which carry the real labels ("Settings", not "More").
      ...routeCommands([...primaryNav, ...moreNav, ...secondaryNav, ...mobileNav]),
      ...actionCommands,
      ...presetCommands,
      ...themeCommands,
    ];
  }, [search.data, sources.data, theme, preset]);

  const ranked = useMemo(() => rankCommands(commands, query), [commands, query]);
  const groups = useMemo(() => groupCommands(ranked), [ranked]);
  /** Flat position of each command, so grouped rendering keeps one index space. */
  const positions = useMemo(
    () => new Map(ranked.map((command, index) => [command.id, index])),
    [ranked],
  );

  // Clamped on read, not corrected in an effect: results shrink as the query
  // narrows and grow when the debounced search lands, and an effect chasing the
  // length would render one frame with the highlight off the end of the list.
  const activeIndex = Math.min(highlighted, Math.max(0, ranked.length - 1));
  const activeCommand = ranked[activeIndex];

  const run = useCallback(
    (command: Command) => {
      onClose();
      if (command.kind === "action") {
        void runAction(command.id);
        return;
      }
      if (command.href) router.push(command.href);
    },
    [onClose, router, runAction],
  );

  // Focus the input on mount, and hand focus back to whatever had it on unmount.
  useEffect(() => {
    previousFocusRef.current = document.activeElement as HTMLElement | null;
    const frame = requestAnimationFrame(() => inputRef.current?.focus());
    return () => {
      cancelAnimationFrame(frame);
      previousFocusRef.current?.focus();
    };
  }, []);

  // Keep the highlighted row on screen as the arrows move it.
  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>('[data-active="true"]')
      ?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  const move = useCallback(
    (delta: number) => {
      if (ranked.length === 0) return;
      // Clamp the stored value the same way the render does before stepping, so
      // a move after the list shrank starts from the visible highlight.
      const from = Math.min(highlighted, ranked.length - 1);
      setHighlighted((from + delta + ranked.length) % ranked.length);
    },
    [highlighted, ranked.length],
  );

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    switch (event.key) {
      case "Escape":
        event.preventDefault();
        onClose();
        return;
      case "ArrowDown":
        event.preventDefault();
        move(1);
        return;
      case "ArrowUp":
        event.preventDefault();
        move(-1);
        return;
      case "Home":
        event.preventDefault();
        setHighlighted(0);
        return;
      case "End":
        event.preventDefault();
        setHighlighted(Math.max(0, ranked.length - 1));
        return;
      case "Enter": {
        event.preventDefault();
        if (activeCommand) run(activeCommand);
        return;
      }
      case "k":
      case "K":
        // The registry cannot re-fire mod+K while focus is in this input (by
        // design — shortcuts stay out of the way of typing), so the
        // toggle-shut half of the binding lives here.
        if (event.metaKey || event.ctrlKey) {
          event.preventDefault();
          onClose();
        }
        return;
    }
  };

  // True both while the debounce is still running and while the request is in
  // flight — from the reader's side those are the same "results are catching up".
  const isSearching =
    trimmedQuery.length >= MIN_QUERY_LENGTH &&
    (search.isFetching || searchQuery !== trimmedQuery);

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center p-4 pt-[12vh]">
      {/* Click-outside target. Hidden from assistive tech and untabbable: the
          input has focus, Escape closes, and a full-screen "close" button
          announced before the results is noise. */}
      <button
        type="button"
        aria-hidden
        tabIndex={-1}
        className="absolute inset-0 bg-bg/70 backdrop-blur-sm"
        onClick={onClose}
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="glass-panel relative z-10 flex max-h-[70vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border shadow-glass"
      >
        <div className="flex items-center gap-3 border-b border-border px-4">
          <Search className="size-4 shrink-0 text-muted" aria-hidden />
          <input
            ref={inputRef}
            type="text"
            role="combobox"
            aria-expanded
            aria-controls={listboxId}
            aria-autocomplete="list"
            aria-activedescendant={
              activeCommand ? `${baseId}-${activeCommand.id}` : undefined
            }
            aria-label="Search series, sources, pages and actions"
            placeholder="Search series, sources, pages and actions…"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setHighlighted(0);
            }}
            onKeyDown={onKeyDown}
            className="h-14 flex-1 bg-transparent text-base text-fg outline-none placeholder:text-muted"
          />
          <Kbd className="hidden sm:inline-flex">Esc</Kbd>
        </div>

        {/* Announces what the eye reads off the list, for screen readers that
            are not tracking aria-activedescendant movement. */}
        <p className="sr-only" role="status">
          {isSearching
            ? "Searching…"
            : `${ranked.length} result${ranked.length === 1 ? "" : "s"}`}
        </p>

        <div
          ref={listRef}
          id={listboxId}
          role="listbox"
          aria-label="Results"
          className="min-h-0 flex-1 overflow-y-auto p-2"
        >
          {ranked.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-muted">
              {isSearching ? "Searching…" : `Nothing matches “${trimmedQuery}”.`}
            </p>
          ) : (
            groups.map(({ group, commands: groupedCommands }) => (
              // `listbox > group > option` is the structure ARIA expects; a
              // ul/li in between would break the relationship.
              <div key={group} role="group" aria-label={group} className="mb-1 last:mb-0">
                <p
                  aria-hidden
                  className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-widest text-muted"
                >
                  {group}
                </p>
                {groupedCommands.map((command) => (
                  <CommandRow
                    key={command.id}
                    id={`${baseId}-${command.id}`}
                    command={command}
                    active={positions.get(command.id) === activeIndex}
                    onHighlight={() => setHighlighted(positions.get(command.id) ?? 0)}
                    onRun={() => run(command)}
                  />
                ))}
              </div>
            ))
          )}
        </div>

        <div className="flex items-center gap-4 border-t border-border px-4 py-2 text-[11px] text-muted">
          <span className="flex items-center gap-1.5">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd>
            to navigate
          </span>
          <span className="flex items-center gap-1.5">
            <Kbd>↵</Kbd>
            to open
          </span>
          <span aria-hidden className="ml-auto hidden sm:block">
            {ranked.length} result{ranked.length === 1 ? "" : "s"}
          </span>
        </div>
      </div>
    </div>
  );
}

interface CommandRowProps {
  id: string;
  command: RankedCommand;
  active: boolean;
  onHighlight: () => void;
  onRun: () => void;
}

/**
 * One result. Not a `<button>`: in the combobox pattern focus stays on the
 * input and options are pointed at with `aria-activedescendant`, so a tabbable
 * control here would put the list in the tab order and break arrow navigation.
 */
function CommandRow({ id, command, active, onHighlight, onRun }: CommandRowProps) {
  // A lookup, not a factory: the two fixed action commands get their own glyph,
  // the rest fall back to one per kind. Theme rows never reach it — they paint a
  // swatch instead.
  const Icon =
    ACTION_ICON[command.id as keyof typeof ACTION_ICON] ?? KIND_ICON[command.kind];

  return (
    <div
      id={id}
      role="option"
      aria-selected={active}
      data-active={active}
      // The pointer must not steal the keyboard's highlight, and mousedown must
      // not blur the input before the click lands.
      onMouseMove={onHighlight}
      onMouseDown={(event) => event.preventDefault()}
      onClick={onRun}
      className={cn(
        "flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors",
        active ? "bg-primary/15" : "hover:bg-surface-2",
      )}
    >
      {command.swatch ? (
        // A palette is best identified by its own colours, not by a generic
        // brush glyph: page background outside, accent inside.
        <span
          aria-hidden
          className="flex size-8 shrink-0 items-center justify-center rounded-md ring-1 ring-border"
          style={{ backgroundColor: command.swatch.bg }}
        >
          <span
            className="size-3 rounded-full"
            style={{ backgroundColor: command.swatch.accent }}
          />
        </span>
      ) : command.imageUrl ? (
        // Cookie-authed covers and source icons resolve via a raw <img> on web.
        // Decorative: the title beside it already names the row, so alt text
        // here would be read twice.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={command.imageUrl}
          alt=""
          aria-hidden
          loading="lazy"
          className="size-8 shrink-0 rounded-md object-cover ring-1 ring-border"
        />
      ) : (
        <span
          aria-hidden
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-md",
            active ? "bg-primary/20 text-primary" : "bg-surface-2 text-muted",
          )}
        >
          <Icon className="size-4" />
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-fg">
          <Highlighted text={command.title} indices={command.match.indices} />
        </span>
        {command.subtitle ? (
          <span className="mt-0.5 block truncate text-xs text-muted">
            {command.subtitle}
          </span>
        ) : null}
      </span>
      {active ? (
        <CornerDownLeft className="size-3.5 shrink-0 text-primary" aria-hidden />
      ) : null}
    </div>
  );
}
