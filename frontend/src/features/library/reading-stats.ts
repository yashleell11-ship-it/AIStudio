/**
 * Everything the statistics screen computes, kept out of React.
 *
 * `vitest.config.ts` runs `src/**\/*.test.ts` in a node environment — there is
 * no DOM and no component renderer in this project's gate — so a number that
 * only exists inside a `.tsx` is a number nothing can assert. The screen is
 * therefore a thin renderer over these functions: request shaping, duration and
 * label formatting, the empty/partial decision, and the full geometry of the
 * activity chart (the SVG component only turns the returned coordinates into
 * elements).
 */

import type {
  DailyReading,
  HourlyReading,
  SourceReading,
  Statistics,
} from "./types";

// ---------------------------------------------------------------------------
// Request shaping
// ---------------------------------------------------------------------------

/** Windows the screen offers. Every one is inside the backend's 1–365 range. */
export const STATISTICS_RANGES = [7, 30, 90] as const;

export type StatisticsRange = (typeof STATISTICS_RANGES)[number];

export const DEFAULT_STATISTICS_RANGE: StatisticsRange = 30;

export const STATISTICS_RANGE_LABELS: Record<StatisticsRange, string> = {
  7: "7 days",
  30: "30 days",
  90: "90 days",
};

/** The backend's own bounds on `tz_offset_minutes` (UTC-12:00 … UTC+14:00). */
const TZ_MIN = -720;
const TZ_MAX = 840;

/**
 * Minutes EAST of UTC for the viewer's clock — what `tz_offset_minutes` wants.
 *
 * `Date.prototype.getTimezoneOffset` reports minutes WEST of UTC (IST, which is
 * UTC+5:30, answers -330), so it is negated here. Getting the sign wrong does
 * not throw: it silently buckets every day eleven hours out, which reads as a
 * plausible-looking chart of the wrong days.
 *
 * The result is clamped to the range the endpoint validates, so an absurd host
 * clock produces a slightly wrong axis rather than a 422 and a blank screen.
 */
export function clientTimezoneOffsetMinutes(date: Date = new Date()): number {
  const offset = -date.getTimezoneOffset();
  if (!Number.isFinite(offset)) return 0;
  return Math.min(TZ_MAX, Math.max(TZ_MIN, Math.trunc(offset)));
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

/**
 * Humane reading time: `"4h 12m"`, not `15120`.
 *
 * Seconds are only shown below a minute, because "3m 40s" of reading is a
 * precision nobody asked for; above an hour the minutes stay, because "4h" for
 * 4h59m loses more than it saves. Hours are never rolled into days — "31h" is
 * a number a reader can picture, "1d 7h" is arithmetic.
 */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0m";
  const whole = Math.floor(seconds);
  if (whole < 60) return `${whole}s`;
  const totalMinutes = Math.floor(whole / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes}m`;
  return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}m`;
}

/** Spoken form for screen readers and `title` text, where "4h 12m" reads badly. */
export function formatDurationLong(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "no time";
  const whole = Math.floor(seconds);
  if (whole < 60) return `${whole} second${whole === 1 ? "" : "s"}`;
  const totalMinutes = Math.floor(whole / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const parts: string[] = [];
  if (hours > 0) parts.push(`${hours} hour${hours === 1 ? "" : "s"}`);
  if (minutes > 0) parts.push(`${minutes} minute${minutes === 1 ? "" : "s"}`);
  return parts.join(" ");
}

/** Thousands separators from the viewer's locale, for the big tabular numbers. */
export function formatCount(value: number): string {
  if (!Number.isFinite(value)) return "0";
  return Math.round(value).toLocaleString();
}

/**
 * `"7 am"` / `"12 pm"` for an hour bucket.
 *
 * Deliberately not locale-formatted: `Intl` would need a real instant, and the
 * only instant available would have to be invented from a date, which is how
 * an off-by-one timezone bug gets in. The hour is already local — the backend
 * bucketed it at the offset we sent — so it is pure arithmetic.
 */
export function formatHourLabel(hour: number): string {
  const h = ((Math.trunc(hour) % 24) + 24) % 24;
  const suffix = h < 12 ? "am" : "pm";
  const twelve = h % 12 === 0 ? 12 : h % 12;
  return `${twelve} ${suffix}`;
}

/** `"7–8 am"` — an hour bucket covers a whole hour, and the ranges make that plain. */
export function formatHourRange(hour: number): string {
  const start = ((Math.trunc(hour) % 24) + 24) % 24;
  return `${formatHourLabel(start)} – ${formatHourLabel(start + 1)}`;
}

const STATUS_LABELS: Record<string, string> = {
  unread: "Unread",
  reading: "Reading",
  completed: "Completed",
  on_hold: "On hold",
  dropped: "Dropped",
  plan_to_read: "Plan to read",
};

/** Order the shelf statuses read in, with anything unrecognised kept at the end. */
const STATUS_ORDER = [
  "reading",
  "plan_to_read",
  "on_hold",
  "completed",
  "dropped",
  "unread",
];

export function readingStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export interface StatusSlice {
  status: string;
  label: string;
  count: number;
  /** Share of the followed set, 0–100. */
  percent: number;
}

/** The reading-status breakdown as an ordered, percentaged list. */
export function readingStatusBreakdown(
  byStatus: Record<string, number>,
): StatusSlice[] {
  const entries = Object.entries(byStatus ?? {}).filter(([, count]) => count > 0);
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  return entries
    .map(([status, count]) => ({
      status,
      label: readingStatusLabel(status),
      count,
      percent: total > 0 ? (count / total) * 100 : 0,
    }))
    .sort((a, b) => {
      const ai = STATUS_ORDER.indexOf(a.status);
      const bi = STATUS_ORDER.indexOf(b.status);
      if (ai !== bi) return (ai < 0 ? STATUS_ORDER.length : ai) - (bi < 0 ? STATUS_ORDER.length : bi);
      return b.count - a.count;
    });
}

// ---------------------------------------------------------------------------
// Shape of the data
// ---------------------------------------------------------------------------

/**
 * Whether `reading_sessions` has anything at all for this profile.
 *
 * Drives the difference between "there is nothing here yet, here is how to
 * start" and a page of zeroes. Uses the ALL-TIME totals, not the window: a
 * reader who last opened a chapter two months ago has a history, it is simply
 * outside the 30 days on screen, and telling them they have never read would
 * be a lie.
 */
export function hasReadingHistory(stats: Statistics): boolean {
  return (stats.totals?.sessions ?? 0) > 0;
}

/** Whether the profile has a library at all, reading history aside. */
export function hasLibrary(stats: Statistics): boolean {
  return (stats.followed_total ?? 0) > 0;
}

/**
 * The screen has genuinely nothing to say: no follows AND nothing ever read.
 *
 * Kept narrow on purpose. A profile that follows series but has not read yet
 * still gets its library section — only the reading half is replaced with its
 * own "start reading" panel, which is a truer picture than blanking the page.
 */
export function isStatisticsEmpty(stats: Statistics): boolean {
  return !hasLibrary(stats) && !hasReadingHistory(stats);
}

/** Whether the selected window is empty even though older history exists. */
export function isWindowEmpty(stats: Statistics): boolean {
  return (stats.window?.sessions ?? 0) === 0;
}

/** The busiest day in the window, or `null` when nothing was read in it. */
export function bestDay(daily: DailyReading[]): DailyReading | null {
  let best: DailyReading | null = null;
  for (const day of daily ?? []) {
    if (day.pages_read <= 0) continue;
    if (best === null || day.pages_read > best.pages_read) best = day;
  }
  return best;
}

/** The hour bucket with the most reading time, or `null` when the window is empty. */
export function peakHour(byHour: HourlyReading[]): HourlyReading | null {
  let best: HourlyReading | null = null;
  for (const bucket of byHour ?? []) {
    if (bucket.sessions <= 0) continue;
    if (
      best === null ||
      bucket.seconds_read > best.seconds_read ||
      (bucket.seconds_read === best.seconds_read && bucket.sessions > best.sessions)
    ) {
      best = bucket;
    }
  }
  return best;
}

/** Days in the window with at least one session — the denominator for "days read". */
export function activeDaysInWindow(daily: DailyReading[]): number {
  return (daily ?? []).reduce((n, day) => n + (day.sessions > 0 ? 1 : 0), 0);
}

export interface SourceShare extends SourceReading {
  /** Share of the window's pages, 0–100. */
  percent: number;
}

/** Per-source rows with their share of the window's pages attached. */
export function sourceShares(bySource: SourceReading[]): SourceShare[] {
  const rows = bySource ?? [];
  const total = rows.reduce((sum, row) => sum + row.pages_read, 0);
  return rows.map((row) => ({
    ...row,
    percent: total > 0 ? (row.pages_read / total) * 100 : 0,
  }));
}

/** Display title for a series row — the raw key is the honest fallback. */
export function seriesTitle(row: { title: string | null; series_key: string }): string {
  const title = row.title?.trim();
  return title && title.length > 0 ? title : row.series_key;
}

/** `Ch 12` / the raw key when the connector gave no number. */
export function chapterLabel(row: {
  chapter_number: number | null;
  chapter_key: string;
}): string {
  return row.chapter_number != null ? `Ch ${row.chapter_number}` : row.chapter_key;
}

// ---------------------------------------------------------------------------
// Activity chart geometry
// ---------------------------------------------------------------------------

/**
 * The gap between gridlines is what has to be nice, not just the top of the
 * axis — round the maximum alone and the labels in between land on fractions.
 *
 * Both axes here count whole things (pages, minutes), so the step is never
 * below 1: a gridline at 0.75 pages is not a quantity, and rounding it for
 * display puts the label "1" on a line that is not at 1.
 *
 * 2.5 earns its place only once the step it makes is in the hundreds (250,
 * 2500, …). The 2→5 jump is the family's widest and at high magnitudes it
 * bites hard — 900 pages forced onto a 0–2000 axis fills less than half of it,
 * where 0–1000 in steps of 250 keeps the shape. Below that the quarter-steps
 * (2.5 is not a whole page; 25 is, but reads worse than what a neighbouring
 * tick count offers) would tip `chooseTickCount` toward a coarser 0–75-style
 * axis over the cleaner five-step one, so they stay out.
 */
const NICE_STEP_MULTIPLIERS = [1, 2, 2.5, 5] as const;

/** The smallest whole nice step that is at least `minStep`. */
function smallestNiceStepAtLeast(minStep: number): number {
  let magnitude = 10 ** Math.max(0, Math.floor(Math.log10(Math.max(1, minStep))));
  for (;;) {
    for (const multiplier of NICE_STEP_MULTIPLIERS) {
      if (multiplier === 2.5 && magnitude < 100) continue;
      const step = multiplier * magnitude;
      if (step >= minStep) return step;
    }
    magnitude *= 10;
  }
}

/**
 * The smallest axis of `count` equal nice steps that still covers `peak`.
 *
 * Forcing the maximum to be a whole multiple of the step is the point: every
 * gridline then falls on a round number in the series' own unit, so the label
 * is the value and not a rounding of it. And with the count fixed by the
 * caller, smallest-covering is the whole choice — any taller axis only adds
 * empty plot above the data.
 */
export function coverAxis(peak: number, count: number): number {
  const steps = Math.max(1, Math.trunc(count));
  if (!Number.isFinite(peak) || peak <= 0) return steps;
  return smallestNiceStepAtLeast(peak / steps) * steps;
}

/** How much taller than its peak an axis had to be drawn. 1 is a perfect fit. */
function axisWaste(peak: number, max: number): number {
  return peak > 0 ? max / peak : 1;
}

/** How far either side of the requested gridline count to look for a better fit. */
const TICK_SEARCH = 2;

/**
 * How many gridlines to divide the plot into, given both series' peaks.
 *
 * The two axes share one set of gridlines — a second set at its own heights
 * would be a grid of near-misses — so the count is a single compromise, and
 * the count that flatters one series can waste half the plot on the other. At
 * 74 pages and 50 minutes, four steps fit pages exactly (0–80) but push time
 * onto an 80-minute axis it only fills to 62%; five steps cost a little slack
 * on pages and land time on 0–50m dead on.
 *
 * So candidates near the requested count are scored by total wasted height and
 * the best wins, ties going to the count actually asked for (they are visited
 * nearest-first and only a strict improvement displaces the incumbent).
 */
export function chooseTickCount(
  peakPages: number,
  peakMinutes: number,
  preferred: number,
): number {
  const target = Math.max(1, Math.trunc(preferred));
  // Nothing was read: one step, so the caller's "no data" copy is not framed
  // by an invented 0–4 scale.
  if (peakPages <= 0 && peakMinutes <= 0) return 1;

  const candidates: number[] = [target];
  for (let offset = 1; offset <= TICK_SEARCH; offset += 1) {
    if (target - offset >= 1) candidates.push(target - offset);
    candidates.push(target + offset);
  }

  let best = target;
  let bestScore = Number.POSITIVE_INFINITY;
  for (const count of candidates) {
    const score =
      axisWaste(peakPages, coverAxis(peakPages, count)) +
      axisWaste(peakMinutes, coverAxis(peakMinutes, count));
    if (score < bestScore) {
      bestScore = score;
      best = count;
    }
  }
  return best;
}

export interface ActivityChartOptions {
  width?: number;
  height?: number;
  /** Room for the left (pages) axis labels. */
  paddingLeft?: number;
  /** Room for the right (time) axis labels. */
  paddingRight?: number;
  paddingTop?: number;
  /** Room for the date labels under the plot. */
  paddingBottom?: number;
  /** Number of gridlines above the baseline. */
  ticks?: number;
  /** Most date labels to draw along the x axis. */
  maxXLabels?: number;
}

export interface ActivityBar {
  date: string;
  x: number;
  y: number;
  width: number;
  height: number;
  pages: number;
  seconds: number;
  sessions: number;
  /** Centre of the day's slot — where the time line's point sits. */
  centerX: number;
}

export interface ActivityPoint {
  date: string;
  x: number;
  y: number;
  seconds: number;
}

export interface ActivityTick {
  y: number;
  /** Left axis: pages. */
  pages: number;
  /** Right axis: seconds. */
  seconds: number;
}

export interface ActivityChart {
  width: number;
  height: number;
  plot: { x: number; y: number; width: number; height: number };
  /** Width of one day's column — the hit target, of which the bar is the visible part. */
  slot: number;
  bars: ActivityBar[];
  points: ActivityPoint[];
  /** `M…L…` through the time points, or `""` when no time was recorded. */
  linePath: string;
  ticks: ActivityTick[];
  xLabels: Array<{ x: number; date: string }>;
  /** Axis maxima; both are whole multiples of their gridline step, and at least 1. */
  maxPages: number;
  maxSeconds: number;
  /** False when there is no day with any reading — the caller draws its own copy. */
  hasData: boolean;
  /**
   * Whether any time was recorded. Separate from `hasData` because a session
   * the client never closed has pages but no seconds, and a right-hand axis
   * scaled for a series that is not drawn invites reading the bars off it.
   */
  hasTime: boolean;
}

/**
 * Turn the dense daily series into coordinates for a two-series chart.
 *
 * Pages are drawn as BARS and reading time as a dashed LINE, on independent
 * scales. The two are told apart by shape, not by colour: a palette that has to
 * survive four reading themes (two of them on paper) cannot also carry the only
 * signal distinguishing the series, and colour alone fails anyone who cannot
 * separate the hues at all. The axis on each side is labelled in its own unit
 * so neither scale has to be guessed.
 *
 * All of it is arithmetic, so all of it is testable; the component only maps
 * the output onto elements.
 */
export function buildActivityChart(
  daily: DailyReading[],
  options: ActivityChartOptions = {},
): ActivityChart {
  const {
    width = 720,
    height = 260,
    paddingLeft = 44,
    paddingRight = 52,
    paddingTop = 16,
    paddingBottom = 28,
    ticks = 4,
    maxXLabels = 6,
  } = options;

  const days = daily ?? [];
  const plot = {
    x: paddingLeft,
    y: paddingTop,
    width: Math.max(1, width - paddingLeft - paddingRight),
    height: Math.max(1, height - paddingTop - paddingBottom),
  };
  const baseline = plot.y + plot.height;

  const peakPages = days.reduce((max, day) => Math.max(max, day.pages_read), 0);
  const peakSeconds = days.reduce((max, day) => Math.max(max, day.seconds_read), 0);
  // Time is scaled in whole minutes: a gridline at "7m 13s" is not a gridline.
  const peakMinutes = Math.ceil(peakSeconds / 60);
  const tickCount = chooseTickCount(peakPages, peakMinutes, ticks);
  const maxPages = coverAxis(peakPages, tickCount);
  const maxSeconds = coverAxis(peakMinutes, tickCount) * 60;
  const hasData = peakPages > 0 || peakSeconds > 0;

  const slot = days.length > 0 ? plot.width / days.length : plot.width;
  // Bars stay slim on a 90-day window and never balloon on a 7-day one.
  const barWidth = Math.max(2, Math.min(slot * 0.62, 22));

  const bars: ActivityBar[] = days.map((day, index) => {
    const centerX = plot.x + slot * (index + 0.5);
    const barHeight =
      day.pages_read > 0
        ? Math.max(2, (day.pages_read / maxPages) * plot.height)
        : 0;
    return {
      date: day.date,
      x: centerX - barWidth / 2,
      y: baseline - barHeight,
      width: barWidth,
      height: barHeight,
      pages: day.pages_read,
      seconds: day.seconds_read,
      sessions: day.sessions,
      centerX,
    };
  });

  const points: ActivityPoint[] =
    peakSeconds > 0
      ? days.map((day, index) => ({
          date: day.date,
          x: plot.x + slot * (index + 0.5),
          y: baseline - (day.seconds_read / maxSeconds) * plot.height,
          seconds: day.seconds_read,
        }))
      : [];

  const linePath = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${round(point.x)} ${round(point.y)}`)
    .join(" ");

  const tickRows: ActivityTick[] = [];
  for (let i = 0; i <= tickCount; i += 1) {
    const fraction = i / tickCount;
    tickRows.push({
      y: baseline - fraction * plot.height,
      pages: maxPages * fraction,
      seconds: maxSeconds * fraction,
    });
  }

  return {
    width,
    height,
    plot,
    slot,
    bars,
    points,
    linePath,
    ticks: tickRows,
    xLabels: pickXLabels(days, plot.x, slot, maxXLabels),
    maxPages,
    maxSeconds,
    hasData,
    hasTime: points.length > 0,
  };
}

/**
 * Up to `max` evenly spaced date labels, always including the first and last
 * day so the axis states the window it actually covers.
 */
function pickXLabels(
  days: DailyReading[],
  plotX: number,
  slot: number,
  max: number,
): Array<{ x: number; date: string }> {
  if (days.length === 0) return [];
  const limit = Math.max(2, Math.trunc(max));
  if (days.length <= limit) {
    return days.map((day, index) => ({
      x: plotX + slot * (index + 0.5),
      date: day.date,
    }));
  }
  const indices = new Set<number>();
  for (let i = 0; i < limit; i += 1) {
    indices.add(Math.round((i * (days.length - 1)) / (limit - 1)));
  }
  return [...indices]
    .sort((a, b) => a - b)
    .map((index) => ({ x: plotX + slot * (index + 0.5), date: days[index].date }));
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}

/**
 * One sentence describing the chart, for `aria-label`.
 *
 * A chart that is only a picture is unreadable to a screen reader, and a
 * per-bar `<title>` is not reachable by one either — so the shape of the data
 * gets said out loud here.
 */
export function activityChartSummary(
  daily: DailyReading[],
  formatDay: (date: string) => string,
): string {
  const days = daily ?? [];
  if (days.length === 0) return "No reading activity to chart.";
  const pages = days.reduce((sum, day) => sum + day.pages_read, 0);
  const seconds = days.reduce((sum, day) => sum + day.seconds_read, 0);
  if (pages === 0 && seconds === 0) {
    return `No pages read in the last ${days.length} days.`;
  }
  const active = activeDaysInWindow(days);
  const peak = bestDay(days);
  const peakPhrase = peak
    ? ` Busiest day ${formatDay(peak.date)}, ${formatCount(peak.pages_read)} pages.`
    : "";
  // Zero recorded seconds means time was never measured (sessions the client
  // never closed), not a measured zero — so the time clause is left unsaid
  // rather than announced as "no time".
  const lead = seconds > 0 ? "Pages read and time spent" : "Pages read";
  const timePhrase = seconds > 0 ? ` and ${formatDurationLong(seconds)}` : "";
  return (
    `${lead} per day over ${days.length} days: ` +
    `${formatCount(pages)} pages${timePhrase} across ` +
    `${active} day${active === 1 ? "" : "s"}.${peakPhrase}`
  );
}

/**
 * Past this many days the per-day time line stops reading as a trend and starts
 * reading as noise laid over the bars, so it thins out and drops its markers.
 */
export const DENSE_CHART_DAYS = 31;

export interface LineStyle {
  strokeWidth: number;
  opacity: number;
  /** Whether to mark each individual day on the line. */
  markers: boolean;
}

/**
 * How heavily to draw the time series for a given number of days.
 *
 * At 7 or 30 days the line is a readable shape and earns full weight; at 90 it
 * is 90 vertices in the same space and a 2px near-white stroke buries the bars
 * underneath it. The bars are the headline metric in both cases, so the line
 * gives way rather than the other way round. Both opacities still clear the
 * 3:1 non-text contrast floor against every theme's card surface.
 */
export function lineStyleFor(pointCount: number): LineStyle {
  return pointCount > DENSE_CHART_DAYS
    ? { strokeWidth: 1.5, opacity: 0.6, markers: false }
    : { strokeWidth: 2, opacity: 0.75, markers: true };
}

/**
 * Bar heights for the 24-hour histogram, as fractions of the busiest hour.
 *
 * A single series, so height alone carries it — but the fraction is returned
 * rather than a colour so the component can encode it twice (height and tint)
 * without inventing a scale of its own.
 */
export function hourlyBars(
  byHour: HourlyReading[],
): Array<HourlyReading & { fraction: number }> {
  const buckets = byHour ?? [];
  const peak = buckets.reduce((max, bucket) => Math.max(max, bucket.seconds_read), 0);
  return buckets.map((bucket) => ({
    ...bucket,
    fraction: peak > 0 ? bucket.seconds_read / peak : 0,
  }));
}
