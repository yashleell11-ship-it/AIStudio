import { describe, expect, it } from "vitest";
import {
  activeDaysInWindow,
  activityChartSummary,
  bestDay,
  buildActivityChart,
  chapterLabel,
  chooseTickCount,
  clientTimezoneOffsetMinutes,
  coverAxis,
  formatCount,
  formatDuration,
  formatDurationLong,
  formatHourLabel,
  formatHourRange,
  hasLibrary,
  hasReadingHistory,
  hourlyBars,
  isStatisticsEmpty,
  isWindowEmpty,
  lineStyleFor,
  peakHour,
  readingStatusBreakdown,
  scopeBreakdowns,
  seriesTitle,
  showsPageCounts,
  sourceShares,
  statisticsScopeNote,
  STATISTICS_RANGES,
} from "./reading-stats";
import type {
  DailyReading,
  HourlyReading,
  RecentSession,
  SeriesReading,
  SourceReading,
  Statistics,
} from "./types";
import type { SourceSummary } from "@/features/sources/types";
import { buildSourceModeIndex, matchesContentMode } from "@/features/content-mode";

function day(date: string, over: Partial<DailyReading> = {}): DailyReading {
  return {
    date,
    sessions: 0,
    pages_read: 0,
    chapters_read: 0,
    series_read: 0,
    seconds_read: 0,
    ...over,
  };
}

function hour(h: number, over: Partial<HourlyReading> = {}): HourlyReading {
  return { hour: h, sessions: 0, pages_read: 0, seconds_read: 0, ...over };
}

function stats(over: Partial<Statistics> = {}): Statistics {
  return {
    followed_total: 0,
    favorites: 0,
    by_reading_status: {},
    chapters_completed: 0,
    range: {
      days: 30,
      since: "2026-08-06T00:00:00",
      until: "2026-09-04T09:00:00",
      timezone_offset_minutes: 330,
      session_cap_seconds: 3600,
    },
    totals: {
      sessions: 0,
      pages_read: 0,
      chapters_read: 0,
      series_read: 0,
      seconds_read: 0,
      first_session_at: null,
      last_session_at: null,
    },
    window: {
      sessions: 0,
      pages_read: 0,
      chapters_read: 0,
      series_read: 0,
      seconds_read: 0,
    },
    streak: { current_days: 0, longest_days: 0, last_active_date: null },
    daily: [],
    by_hour: Array.from({ length: 24 }, (_, h) => hour(h)),
    by_source: [],
    by_series: [],
    recent_sessions: [],
    ...over,
  };
}

// --- request shaping -------------------------------------------------------

describe("clientTimezoneOffsetMinutes", () => {
  it("negates getTimezoneOffset so IST sends +330, not -330", () => {
    // `getTimezoneOffset` counts minutes WEST of UTC; the endpoint wants EAST.
    // The wrong sign does not error, it just buckets the wrong days.
    const ist = { getTimezoneOffset: () => -330 } as Date;
    expect(clientTimezoneOffsetMinutes(ist)).toBe(330);

    const losAngeles = { getTimezoneOffset: () => 480 } as Date;
    expect(clientTimezoneOffsetMinutes(losAngeles)).toBe(-480);
  });

  it("clamps to the range the backend validates", () => {
    expect(clientTimezoneOffsetMinutes({ getTimezoneOffset: () => -2000 } as Date)).toBe(840);
    expect(clientTimezoneOffsetMinutes({ getTimezoneOffset: () => 2000 } as Date)).toBe(-720);
  });

  it("falls back to UTC for a nonsense host clock", () => {
    expect(clientTimezoneOffsetMinutes({ getTimezoneOffset: () => NaN } as Date)).toBe(0);
  });

  it("only offers windows the endpoint accepts", () => {
    for (const range of STATISTICS_RANGES) {
      expect(range).toBeGreaterThanOrEqual(1);
      expect(range).toBeLessThanOrEqual(365);
    }
  });
});

// --- formatting ------------------------------------------------------------

describe("formatDuration", () => {
  it("renders reading time humanely, never as raw seconds", () => {
    expect(formatDuration(15120)).toBe("4h 12m");
    expect(formatDuration(3600)).toBe("1h");
    expect(formatDuration(7260)).toBe("2h 1m");
    expect(formatDuration(720)).toBe("12m");
    expect(formatDuration(45)).toBe("45s");
  });

  it("does not roll hours into days", () => {
    expect(formatDuration(112_500)).toBe("31h 15m");
  });

  it("reports nothing read as 0m rather than a blank or NaN", () => {
    expect(formatDuration(0)).toBe("0m");
    expect(formatDuration(-10)).toBe("0m");
    expect(formatDuration(Number.NaN)).toBe("0m");
  });

  it("spells the same value out for screen readers", () => {
    expect(formatDurationLong(15120)).toBe("4 hours 12 minutes");
    expect(formatDurationLong(3600)).toBe("1 hour");
    expect(formatDurationLong(60)).toBe("1 minute");
    expect(formatDurationLong(0)).toBe("no time");
  });
});

describe("hour labels", () => {
  it("names an hour bucket without inventing a date to format", () => {
    expect(formatHourLabel(0)).toBe("12 am");
    expect(formatHourLabel(7)).toBe("7 am");
    expect(formatHourLabel(12)).toBe("12 pm");
    expect(formatHourLabel(23)).toBe("11 pm");
  });

  it("states the whole hour a bucket covers, wrapping at midnight", () => {
    expect(formatHourRange(7)).toBe("7 am – 8 am");
    expect(formatHourRange(23)).toBe("11 pm – 12 am");
  });
});

describe("formatCount", () => {
  it("groups thousands so a five-digit page count is readable", () => {
    expect(formatCount(15120)).toBe((15120).toLocaleString());
    expect(formatCount(Number.NaN)).toBe("0");
  });
});

describe("readingStatusBreakdown", () => {
  it("orders by shelf meaning, percentages the counts and drops zeroes", () => {
    const rows = readingStatusBreakdown({
      completed: 2,
      reading: 6,
      dropped: 0,
      plan_to_read: 2,
    });
    expect(rows.map((r) => r.status)).toEqual(["reading", "plan_to_read", "completed"]);
    expect(rows[0]).toMatchObject({ label: "Reading", count: 6, percent: 60 });
  });

  it("keeps an unrecognised status at the end under its raw name", () => {
    const rows = readingStatusBreakdown({ rereading: 1, reading: 1 });
    expect(rows.map((r) => r.status)).toEqual(["reading", "rereading"]);
    expect(rows[1].label).toBe("rereading");
  });

  it("survives an empty breakdown without dividing by zero", () => {
    expect(readingStatusBreakdown({})).toEqual([]);
  });
});

// --- shape of the data -----------------------------------------------------

describe("empty-state decisions", () => {
  it("calls a brand-new profile empty", () => {
    expect(isStatisticsEmpty(stats())).toBe(true);
  });

  it("does not call a profile with follows empty just because it has not read", () => {
    const withFollows = stats({ followed_total: 4 });
    expect(hasLibrary(withFollows)).toBe(true);
    expect(hasReadingHistory(withFollows)).toBe(false);
    expect(isStatisticsEmpty(withFollows)).toBe(false);
  });

  it("uses all-time totals, so history older than the window still counts", () => {
    // Read a lot two months ago, nothing in the last 30 days. Saying "you have
    // never read anything" here would be a lie.
    const lapsed = stats({
      totals: {
        sessions: 40,
        pages_read: 900,
        chapters_read: 60,
        series_read: 3,
        seconds_read: 40_000,
        first_session_at: "2026-05-01T10:00:00",
        last_session_at: "2026-07-02T10:00:00",
      },
    });
    expect(hasReadingHistory(lapsed)).toBe(true);
    expect(isStatisticsEmpty(lapsed)).toBe(false);
    expect(isWindowEmpty(lapsed)).toBe(true);
  });
});

describe("window summaries", () => {
  const daily = [
    day("2026-09-01", { sessions: 2, pages_read: 30, seconds_read: 1200 }),
    day("2026-09-02"),
    day("2026-09-03", { sessions: 5, pages_read: 74, seconds_read: 3000 }),
    day("2026-09-04", { sessions: 1, pages_read: 12, seconds_read: 400 }),
  ];

  it("finds the busiest day by pages", () => {
    expect(bestDay(daily)?.date).toBe("2026-09-03");
  });

  it("counts only days with a session as active", () => {
    expect(activeDaysInWindow(daily)).toBe(3);
  });

  it("returns null for a window with nothing in it", () => {
    expect(bestDay([day("2026-09-01"), day("2026-09-02")])).toBeNull();
    expect(bestDay([])).toBeNull();
  });
});

describe("peakHour", () => {
  it("picks the hour with the most reading time", () => {
    const buckets = [
      hour(7, { sessions: 4, seconds_read: 600 }),
      hour(22, { sessions: 2, seconds_read: 3000 }),
      hour(23, { sessions: 9, seconds_read: 100 }),
    ];
    expect(peakHour(buckets)?.hour).toBe(22);
  });

  it("breaks a tie on session count", () => {
    const buckets = [
      hour(7, { sessions: 1, seconds_read: 600 }),
      hour(21, { sessions: 5, seconds_read: 600 }),
    ];
    expect(peakHour(buckets)?.hour).toBe(21);
  });

  it("is null when nothing was read", () => {
    expect(peakHour(Array.from({ length: 24 }, (_, h) => hour(h)))).toBeNull();
  });
});

describe("sourceShares", () => {
  const rows: SourceReading[] = [
    {
      source_id: "asura",
      name: "Asura Scans",
      sessions: 10,
      pages_read: 150,
      chapters_read: 8,
      series_read: 2,
      seconds_read: 5000,
    },
    {
      source_id: "flame",
      name: "Flame Scans",
      sessions: 4,
      pages_read: 50,
      chapters_read: 3,
      series_read: 1,
      seconds_read: 1500,
    },
  ];

  it("attaches each source's share of the window's pages", () => {
    const shares = sourceShares(rows);
    expect(shares[0].percent).toBe(75);
    expect(shares[1].percent).toBe(25);
  });

  it("does not divide by zero when the window recorded no pages", () => {
    const zeroed = rows.map((row) => ({ ...row, pages_read: 0 }));
    expect(sourceShares(zeroed).every((row) => row.percent === 0)).toBe(true);
    expect(sourceShares([])).toEqual([]);
  });
});

describe("scopeBreakdowns", () => {
  // The real index the screen builds, so the scoping under test is the one
  // production runs — including "a source the listing does not carry is manga".
  const sources: SourceSummary[] = [
    {
      id: "asura",
      name: "Asura Scans",
      description: "",
      browsable: true,
      supports_import: false,
      content_kind: "manga",
    },
    {
      id: "novelbin",
      name: "NovelBin",
      description: "",
      browsable: true,
      supports_import: false,
      content_kind: "novel",
    },
  ];
  const index = buildSourceModeIndex(sources);
  const keep = (mode: "manga" | "novel") => (sourceId: string) =>
    matchesContentMode(sourceId, index, mode);

  const bySource: SourceReading[] = [
    {
      source_id: "asura",
      name: "Asura Scans",
      sessions: 10,
      pages_read: 150,
      chapters_read: 8,
      series_read: 2,
      seconds_read: 5000,
    },
    {
      source_id: "novelbin",
      name: "NovelBin",
      sessions: 6,
      pages_read: 50,
      chapters_read: 4,
      series_read: 1,
      seconds_read: 2400,
    },
  ];

  const seriesRow = (source_id: string, series_key: string): SeriesReading => ({
    source_id,
    series_key,
    title: series_key,
    cover_url: null,
    last_read_at: null,
    sessions: 1,
    pages_read: 10,
    chapters_read: 1,
    seconds_read: 300,
  });

  const session = (source_id: string): RecentSession => ({
    source_id,
    series_key: `${source_id}/s`,
    chapter_key: `${source_id}/s/1`,
    chapter_number: 1,
    title: null,
    pages_read: 5,
    seconds_read: 200,
    started_at: "2026-09-04T08:00:00",
    ended_at: "2026-09-04T08:04:00",
  });

  const payload = stats({
    followed_total: 12,
    chapters_completed: 40,
    totals: {
      sessions: 16,
      pages_read: 200,
      chapters_read: 12,
      series_read: 3,
      seconds_read: 7400,
      first_session_at: "2026-01-01T00:00:00",
      last_session_at: "2026-09-04T08:04:00",
    },
    window: {
      sessions: 16,
      pages_read: 200,
      chapters_read: 12,
      series_read: 3,
      seconds_read: 7400,
    },
    streak: { current_days: 9, longest_days: 21, last_active_date: "2026-09-04" },
    daily: [day("2026-09-04", { sessions: 16, pages_read: 200 })],
    by_source: bySource,
    by_series: [seriesRow("asura", "solo-leveling"), seriesRow("novelbin", "shadow-slave")],
    recent_sessions: [session("asura"), session("novelbin"), session("gone")],
  });

  it("scopes all three source-carrying lists, not just one of them", () => {
    const novels = scopeBreakdowns(payload, keep("novel"));
    expect(novels.by_source.map((row) => row.source_id)).toEqual(["novelbin"]);
    expect(novels.by_series.map((row) => row.series_key)).toEqual(["shadow-slave"]);
    expect(novels.recent_sessions.map((row) => row.source_id)).toEqual(["novelbin"]);

    const manga = scopeBreakdowns(payload, keep("manga"));
    expect(manga.by_source.map((row) => row.source_id)).toEqual(["asura"]);
    expect(manga.by_series.map((row) => row.series_key)).toEqual(["solo-leveling"]);
    // An id the source listing no longer carries reads as manga, so a removed
    // connector's history keeps showing where it shows today.
    expect(manga.recent_sessions.map((row) => row.source_id)).toEqual(["asura", "gone"]);
  });

  it("leaves every aggregate exactly as the server computed it", () => {
    // The deliberate half of the split: totals, streak, daily and the clock
    // describe the reader across both media and are not rebuildable per mode.
    const novels = scopeBreakdowns(payload, keep("novel"));
    expect(novels.totals).toEqual(payload.totals);
    expect(novels.window).toEqual(payload.window);
    expect(novels.streak).toEqual(payload.streak);
    expect(novels.daily).toEqual(payload.daily);
    expect(novels.by_hour).toEqual(payload.by_hour);
    expect(novels.followed_total).toBe(payload.followed_total);
    expect(novels.chapters_completed).toBe(payload.chapters_completed);
  });

  it("re-bases the source bars on the mode, so they still read as shares", () => {
    // 50 of 200 pages overall, but all of the novel reading — the bar has to
    // say 100%, not 25%, or "Where you read" describes a list it is not showing.
    const shares = sourceShares(scopeBreakdowns(payload, keep("novel")).by_source);
    expect(shares).toHaveLength(1);
    expect(shares[0].percent).toBe(100);
  });

  it("changes nothing while novels are disabled", () => {
    // `keepSource` is true for every row on a dark deployment, so the screen
    // renders the identical payload however many lists are wired through here.
    const scoped = scopeBreakdowns(payload, () => true);
    expect(scoped).toEqual(payload);
  });

  it("survives a payload whose breakdowns are empty", () => {
    const bare = scopeBreakdowns(stats(), keep("novel"));
    expect(bare.by_source).toEqual([]);
    expect(bare.by_series).toEqual([]);
    expect(bare.recent_sessions).toEqual([]);
  });
});

describe("labels for rows the follow table no longer covers", () => {
  it("falls back to the raw series key once a series is unfollowed", () => {
    expect(seriesTitle({ title: "Nano Machine", series_key: "series/nm" })).toBe(
      "Nano Machine",
    );
    expect(seriesTitle({ title: null, series_key: "series/nm" })).toBe("series/nm");
    expect(seriesTitle({ title: "   ", series_key: "series/nm" })).toBe("series/nm");
  });

  it("falls back to the chapter key when the connector gave no number", () => {
    expect(chapterLabel({ chapter_number: 210, chapter_key: "ch/210" })).toBe("Ch 210");
    expect(chapterLabel({ chapter_number: null, chapter_key: "ch/extra" })).toBe("ch/extra");
  });
});

// --- chart geometry --------------------------------------------------------

describe("coverAxis", () => {
  it("covers the peak with a whole number of nice steps", () => {
    expect(coverAxis(74, 4)).toBe(80);
    expect(coverAxis(40, 4)).toBe(40);
    expect(coverAxis(137, 3)).toBe(150);
    expect(coverAxis(900, 4)).toBe(1000);
  });

  it("divides evenly, so every gridline label is the value and not a rounding", () => {
    // The old axis rounded only the maximum: a peak of 3 became a 0-5 axis, and
    // four gridlines over it read 0, 1, 3, 4, 5 for values 0, 1.25, 2.5, 3.75, 5.
    for (const count of [1, 2, 3, 4, 5, 6]) {
      for (const peak of [1, 2, 3, 5, 8, 12, 30, 45, 74, 137, 900]) {
        const max = coverAxis(peak, count);
        expect(max).toBeGreaterThanOrEqual(peak);
        expect(Number.isInteger(max / count)).toBe(true);
      }
    }
  });

  it("never returns zero, so nothing downstream divides by it", () => {
    expect(coverAxis(0, 4)).toBe(4);
    expect(coverAxis(-5, 1)).toBe(1);
    expect(coverAxis(Number.NaN, 3)).toBe(3);
  });
});

describe("chooseTickCount", () => {
  it("spends gridlines where they waste the least of the plot", () => {
    // Four steps fit 74 pages exactly (0-80) but strand 50 minutes on a
    // 0-80m axis; five costs pages a little slack and lands time dead on.
    expect(chooseTickCount(74, 50, 4)).toBe(5);
    expect(coverAxis(74, 5)).toBe(100);
    expect(coverAxis(50, 5)).toBe(50);
  });

  it("keeps the requested count when it already fits both series", () => {
    expect(chooseTickCount(40, 18, 4)).toBe(4);
  });

  it("collapses to a single step when nothing was read", () => {
    // Otherwise an empty chart is framed by an invented 0-4 scale.
    expect(chooseTickCount(0, 0, 4)).toBe(1);
    expect(coverAxis(0, 1)).toBe(1);
  });

  it("stays sane on the tiny peaks a brand-new profile actually has", () => {
    for (const peak of [1, 2, 3]) {
      const count = chooseTickCount(peak, peak, 4);
      expect(count).toBeGreaterThanOrEqual(1);
      expect(coverAxis(peak, count) / count).toBeGreaterThanOrEqual(1);
    }
  });

  it("never leaves an axis less than half full for any real reading", () => {
    // The invariant the whole tick search exists for. Swept, not sampled,
    // because the failure mode is a family gap at one particular peak (the old
    // step family put 900 pages on a 0–2000 axis and no spot check caught it).
    // Degenerate one-minute windows may reach 2.5×: a 1m axis doubles its
    // waste with every extra gridline, so it pins the count low and the pages
    // axis eats the slack — that trade is deliberate, and it is bounded too.
    for (const target of [3, 4]) {
      for (let pages = 1; pages <= 400; pages += 1) {
        for (const minutes of [1, 2, 5, 12, 18, 50, 90, 240]) {
          const count = chooseTickCount(pages, minutes, target);
          const wastePages = coverAxis(pages, count) / pages;
          const wasteMinutes = coverAxis(minutes, count) / minutes;
          expect(wastePages).toBeGreaterThanOrEqual(1);
          expect(wasteMinutes).toBeGreaterThanOrEqual(1);
          const bound = pages >= 5 && minutes >= 5 ? 2 : 2.5;
          expect(Math.max(wastePages, wasteMinutes)).toBeLessThanOrEqual(bound);
        }
      }
    }
  });
});

describe("buildActivityChart", () => {
  const daily = [
    day("2026-09-01", { sessions: 2, pages_read: 30, seconds_read: 1200 }),
    day("2026-09-02"),
    day("2026-09-03", { sessions: 5, pages_read: 74, seconds_read: 3000 }),
    day("2026-09-04", { sessions: 1, pages_read: 12, seconds_read: 400 }),
  ];
  const chart = buildActivityChart(daily, { width: 400, height: 200 });

  it("keeps every bar inside the plot and on the baseline", () => {
    const baseline = chart.plot.y + chart.plot.height;
    expect(chart.bars).toHaveLength(4);
    for (const bar of chart.bars) {
      expect(bar.x).toBeGreaterThanOrEqual(chart.plot.x - 0.001);
      expect(bar.x + bar.width).toBeLessThanOrEqual(
        chart.plot.x + chart.plot.width + 0.001,
      );
      expect(Math.round(bar.y + bar.height)).toBe(Math.round(baseline));
      expect(bar.y).toBeGreaterThanOrEqual(chart.plot.y - 0.001);
    }
  });

  it("scales bar heights against the nice-rounded page maximum", () => {
    expect(chart.maxPages).toBe(100);
    const peak = chart.bars[2];
    expect(peak.height).toBeCloseTo((74 / 100) * chart.plot.height, 5);
  });

  it("gives a day with no reading no bar at all", () => {
    expect(chart.bars[1].height).toBe(0);
  });

  it("still draws a visible sliver for a day with one page", () => {
    const tiny = buildActivityChart(
      [day("2026-09-01", { sessions: 1, pages_read: 1, seconds_read: 20 }),
       day("2026-09-02", { sessions: 9, pages_read: 900, seconds_read: 9000 })],
      { width: 400, height: 200 },
    );
    expect(tiny.bars[0].height).toBeGreaterThanOrEqual(2);
  });

  it("puts the time line on its own scale, rounded to whole minutes", () => {
    // Peak 3000s = 50 minutes -> nice max 50 minutes = 3000 seconds.
    expect(chart.maxSeconds).toBe(3000);
    expect(chart.points).toHaveLength(4);
    expect(chart.points[2].y).toBeCloseTo(chart.plot.y, 5);
    expect(chart.linePath.startsWith("M")).toBe(true);
    expect(chart.linePath.split("L")).toHaveLength(4);
  });

  it("centres each line point over its bar so the two series line up", () => {
    chart.points.forEach((point, index) => {
      expect(point.x).toBeCloseTo(chart.bars[index].centerX, 5);
    });
  });

  it("labels both axes in their own unit at every gridline", () => {
    expect(chart.ticks).toHaveLength(6);
    expect(chart.ticks[0].pages).toBe(0);
    expect(chart.ticks[0].y).toBeCloseTo(chart.plot.y + chart.plot.height, 5);
    expect(chart.ticks[5].pages).toBe(chart.maxPages);
    expect(chart.ticks[5].seconds).toBe(chart.maxSeconds);
    expect(chart.ticks[5].y).toBeCloseTo(chart.plot.y, 5);

    // Every gridline in between is a whole page and a whole minute, so the
    // label under it is the value rather than a rounding of it.
    for (const tick of chart.ticks) {
      expect(Number.isInteger(tick.pages)).toBe(true);
      expect(Number.isInteger(tick.seconds / 60)).toBe(true);
    }
  });

  it("thins the date labels on a long window but keeps the first and last day", () => {
    const ninety = buildActivityChart(
      Array.from({ length: 90 }, (_, i) =>
        day(`2026-06-${String((i % 28) + 1).padStart(2, "0")}`),
      ),
      { width: 720, maxXLabels: 6 },
    );
    expect(ninety.xLabels).toHaveLength(6);
    expect(ninety.xLabels[0].x).toBeCloseTo(ninety.bars[0].centerX, 5);
    expect(ninety.xLabels[5].x).toBeCloseTo(ninety.bars[89].centerX, 5);
  });

  it("labels every day when the window is short enough to fit them", () => {
    expect(chart.xLabels.map((l) => l.date)).toEqual(daily.map((d) => d.date));
  });

  it("reports no data rather than drawing a flat line for an empty window", () => {
    const empty = buildActivityChart([day("2026-09-01"), day("2026-09-02")]);
    expect(empty.hasData).toBe(false);
    expect(empty.points).toEqual([]);
    expect(empty.linePath).toBe("");
    expect(empty.maxPages).toBe(1);
  });

  it("handles a one-day and a zero-day window without producing NaN", () => {
    const one = buildActivityChart([
      day("2026-09-04", { sessions: 1, pages_read: 5, seconds_read: 300 }),
    ]);
    expect(Number.isFinite(one.bars[0].x)).toBe(true);
    expect(Number.isFinite(one.bars[0].height)).toBe(true);

    const none = buildActivityChart([]);
    expect(none.bars).toEqual([]);
    expect(none.xLabels).toEqual([]);
    expect(none.hasData).toBe(false);
  });

  it("keeps bars slim on a 90-day window and capped on a 7-day one", () => {
    const wide = buildActivityChart(
      Array.from({ length: 7 }, (_, i) => day(`2026-09-0${i + 1}`)),
      { width: 900 },
    );
    expect(wide.bars[0].width).toBeLessThanOrEqual(22);

    const dense = buildActivityChart(
      Array.from({ length: 90 }, (_, i) => day(`2026-09-${String(i + 1)}`)),
      { width: 400 },
    );
    expect(dense.bars[0].width).toBeGreaterThanOrEqual(2);
  });
});

describe("activityChartSummary", () => {
  const label = (date: string) => date;

  it("says out loud what the picture shows", () => {
    const summary = activityChartSummary(
      [
        day("2026-09-01", { sessions: 2, pages_read: 30, seconds_read: 1200 }),
        day("2026-09-02"),
        day("2026-09-03", { sessions: 5, pages_read: 74, seconds_read: 3000 }),
      ],
      label,
    );
    expect(summary).toContain("104 pages");
    expect(summary).toContain("1 hour 10 minutes");
    expect(summary).toContain("2 days");
    expect(summary).toContain("Busiest day 2026-09-03");
  });

  it("does not claim 'no time' for pages whose time was never measured", () => {
    // A session the client never closed has pages but zero seconds; "no time"
    // would announce a measured zero for a series that was never measured.
    const summary = activityChartSummary(
      [day("2026-09-01", { sessions: 1, pages_read: 30 })],
      label,
    );
    expect(summary).toContain("30 pages");
    expect(summary).not.toContain("no time");
    expect(summary).not.toContain("time spent");
  });

  it("says nothing was read instead of describing an empty picture", () => {
    expect(activityChartSummary([day("2026-09-01")], label)).toBe(
      "No pages read in the last 1 days.",
    );
    expect(activityChartSummary([], label)).toBe("No reading activity to chart.");
  });
});

describe("hourlyBars", () => {
  it("scales each hour against the busiest one", () => {
    const bars = hourlyBars([
      hour(7, { sessions: 1, seconds_read: 600 }),
      hour(22, { sessions: 3, seconds_read: 2400 }),
    ]);
    expect(bars[0].fraction).toBe(0.25);
    expect(bars[1].fraction).toBe(1);
  });

  it("gives every hour a zero fraction when nothing was read", () => {
    const bars = hourlyBars(Array.from({ length: 24 }, (_, h) => hour(h)));
    expect(bars).toHaveLength(24);
    expect(bars.every((b) => b.fraction === 0)).toBe(true);
  });
});

describe("lineStyleFor", () => {
  it("gives the time series full weight and per-day markers on a readable window", () => {
    expect(lineStyleFor(7)).toEqual({ strokeWidth: 2, opacity: 0.75, markers: true });
    expect(lineStyleFor(30)).toEqual({ strokeWidth: 2, opacity: 0.75, markers: true });
  });

  it("thins it and drops the markers once the line is more noise than trend", () => {
    // 90 vertices of a 2px near-white stroke bury the bars underneath them.
    expect(lineStyleFor(90)).toEqual({ strokeWidth: 1.5, opacity: 0.6, markers: false });
  });

  it("never draws the line so faint it fails non-text contrast", () => {
    for (const count of [0, 7, 30, 31, 32, 90, 365]) {
      expect(lineStyleFor(count).opacity).toBeGreaterThanOrEqual(0.6);
      expect(lineStyleFor(count).strokeWidth).toBeGreaterThanOrEqual(1.5);
    }
  });
});


describe("reading units", () => {
  it("prints page counts in manga mode and on a deployment with novels off", () => {
    expect(showsPageCounts("manga", true)).toBe(true);
    expect(showsPageCounts("manga", false)).toBe(true);
    // With the flag off the mode is forced to manga anyway, but a stored
    // "novel" must not be able to change what a manga-only app renders.
    expect(showsPageCounts("novel", false)).toBe(true);
  });

  it("drops page counts in Novels mode, where the number is not pages", () => {
    // `last_page` is a percent-of-chapter bucket for prose, capped at 100 per
    // chapter, so one novel chapter can register 100 "pages" against a manga
    // chapter's twenty.
    expect(showsPageCounts("novel", true)).toBe(false);
  });

  it("says nothing about scope or units when novels are off", () => {
    expect(statisticsScopeNote("manga", false)).toBeNull();
    expect(statisticsScopeNote("novel", false)).toBeNull();
  });

  it("names the mode the lists are scoped to, and warns that pages mix", () => {
    const novel = statisticsScopeNote("novel", true);
    expect(novel).toContain("novels only");
    expect(novel).toContain("two different things");
    expect(statisticsScopeNote("manga", true)).toContain("manga only");
  });
});
