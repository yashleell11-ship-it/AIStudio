/**
 * The command palette's data model and ranking.
 *
 * Free of React and of `lucide-react` on purpose: the palette's ordering is the
 * part worth testing, and it should be testable in a node environment without
 * dragging a component tree (or an icon set) in. The view maps `kind` to an
 * icon; this module never names one.
 */

import { fuzzyMatchAny, type FuzzyMatch } from "./fuzzy";

/**
 * What running the command does.
 * - `route`  — go to a static app route.
 * - `series` — go to a series found in the library search.
 * - `source` — go to an installed source's browse screen.
 * - `action` — run something in place (toggle the theme, sign out, …).
 */
export type CommandKind = "route" | "series" | "source" | "action";

export interface Command {
  /** Stable and unique across the whole palette; also the React key. */
  id: string;
  title: string;
  subtitle?: string;
  /** Section header in the list. */
  group: string;
  kind: CommandKind;
  /** Set for everything except `action`. */
  href?: string;
  /** Extra text the query may match, never displayed. */
  keywords?: string[];
  /** Absolute cover/icon URL, when the row should show artwork. */
  imageUrl?: string | null;
}

export interface RankedCommand extends Command {
  match: FuzzyMatch;
}

/** Relative order of groups in the list, best-first. Unknown groups sink. */
const GROUP_ORDER = ["Library", "Sources", "Go to", "Actions"] as const;

function groupRank(group: string): number {
  const index = (GROUP_ORDER as readonly string[]).indexOf(group);
  return index === -1 ? GROUP_ORDER.length : index;
}

/**
 * Commands that match `query`, best-first, capped at `limit`.
 *
 * With an empty query every command matches with score 0, so the result is the
 * declaration order grouped by {@link GROUP_ORDER} — which is what the palette
 * shows before anything is typed. Ties break on group, then on the order the
 * caller supplied, so the list never reshuffles for equally good hits.
 */
export function rankCommands(
  commands: readonly Command[],
  query: string,
  limit = 40,
): RankedCommand[] {
  const ranked: { command: RankedCommand; index: number }[] = [];

  commands.forEach((command, index) => {
    const secondary = [...(command.keywords ?? [])];
    if (command.subtitle) secondary.push(command.subtitle);
    const match = fuzzyMatchAny(query, command.title, secondary);
    if (match === null) return;
    ranked.push({ command: { ...command, match }, index });
  });

  ranked.sort((a, b) => {
    if (b.command.match.score !== a.command.match.score) {
      return b.command.match.score - a.command.match.score;
    }
    const groupDelta = groupRank(a.command.group) - groupRank(b.command.group);
    if (groupDelta !== 0) return groupDelta;
    return a.index - b.index;
  });

  return ranked.slice(0, limit).map((entry) => entry.command);
}

/**
 * Ranked commands split into their groups, in {@link GROUP_ORDER}.
 *
 * Grouping happens AFTER ranking so a section only appears when something in it
 * matched, and the sections themselves are ordered by their best hit — typing a
 * series title puts Library first, typing "sign" puts Actions first.
 */
export function groupCommands(
  ranked: readonly RankedCommand[],
): { group: string; commands: RankedCommand[] }[] {
  const groups = new Map<string, RankedCommand[]>();
  for (const command of ranked) {
    const existing = groups.get(command.group);
    if (existing) existing.push(command);
    else groups.set(command.group, [command]);
  }
  return Array.from(groups.entries()).map(([group, commands]) => ({
    group,
    commands,
  }));
}

/** A nav entry, narrowed to what the palette needs from `@/config/nav`. */
export interface RouteSource {
  href: string;
  label: string;
}

/**
 * One command per app route.
 *
 * De-duplicated by `href`: the nav config lists a few destinations in more than
 * one place (Settings is both a sidebar footer item and the mobile "More" tab),
 * and the palette must offer each exactly once.
 */
export function routeCommands(routes: readonly RouteSource[]): Command[] {
  const seen = new Set<string>();
  const commands: Command[] = [];
  for (const route of routes) {
    if (seen.has(route.href)) continue;
    seen.add(route.href);
    commands.push({
      id: `route:${route.href}`,
      title: route.label,
      subtitle: route.href,
      group: "Go to",
      kind: "route",
      href: route.href,
      keywords: [route.href.replace(/\//g, " ").trim()],
    });
  }
  return commands;
}
