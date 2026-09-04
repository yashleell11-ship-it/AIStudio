"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  activityChartSummary,
  buildActivityChart,
  formatCount,
  formatDuration,
  formatDurationLong,
  lineStyleFor,
} from "@/features/library/reading-stats";
import type { DailyReading } from "@/features/library/types";
import { formatCalendarDay } from "@/lib/utc-time";

/**
 * Pages read and time spent, per day, as one chart.
 *
 * Two series on independent scales, told apart by SHAPE — solid bars for pages,
 * a dashed line for time — not by colour. The app ships four reading themes,
 * two of them on paper, so a hue that separates the series in one can collapse
 * in another; and colour alone separates nothing for a reader who cannot tell
 * the hues apart. The legend repeats the same two marks so the key and the plot
 * cannot drift, and each axis is labelled in its own unit.
 *
 * Everything is inline SVG painted from theme tokens via `currentColor`: a
 * strict CSP rules out a chart CDN, the app is self-hosted, and `package.json`
 * carries no charting dependency worth adding one for.
 *
 * All of the arithmetic is in `buildActivityChart`, which the node test gate
 * can actually assert on; this file only turns coordinates into elements.
 */

const HEIGHT = 260;
const COMPACT_HEIGHT = 200;
const FALLBACK_WIDTH = 720;

/** Measured content width, so the chart is drawn 1:1 and its text is never scaled. */
function useMeasuredWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(FALLBACK_WIDTH);

  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    const measure = () => setWidth(Math.max(240, node.clientWidth));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return { ref, width };
}

function shortDay(date: string): string {
  return formatCalendarDay(date, {
    format: { month: "short", day: "numeric" },
    invalid: date,
  });
}

function longDay(date: string): string {
  return formatCalendarDay(date, {
    format: { weekday: "short", month: "short", day: "numeric" },
    invalid: date,
  });
}

export function ActivityChart({ daily }: { daily: DailyReading[] }) {
  const { ref, width } = useMeasuredWidth();
  const compact = width < 520;
  const height = compact ? COMPACT_HEIGHT : HEIGHT;

  const chart = useMemo(
    () =>
      buildActivityChart(daily, {
        width,
        height,
        paddingLeft: compact ? 34 : 44,
        paddingRight: compact ? 42 : 54,
        paddingTop: 14,
        paddingBottom: 26,
        ticks: compact ? 3 : 4,
        maxXLabels: compact ? 4 : 6,
      }),
    [daily, width, height, compact],
  );

  const summary = useMemo(() => activityChartSummary(daily, longDay), [daily]);
  const line = lineStyleFor(chart.points.length);
  const baseline = chart.plot.y + chart.plot.height;

  return (
    <div ref={ref} className="w-full">
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
        <span className="inline-flex items-center gap-2">
          <span aria-hidden className="h-3.5 w-2 rounded-sm bg-primary" />
          Pages read
        </span>
        {chart.hasTime ? (
          <span className="inline-flex items-center gap-2">
            <svg aria-hidden width="22" height="8" viewBox="0 0 22 8" className="text-fg">
              <path
                d="M0 4 H22"
                stroke="currentColor"
                strokeWidth="2"
                strokeDasharray="5 4"
                fill="none"
              />
              <rect x="8" y="1" width="6" height="6" fill="currentColor" />
            </svg>
            Time read
          </span>
        ) : null}
      </div>

      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={summary}
        className="block"
      >
        {/* Gridlines and the two axis scales. */}
        <g className="text-border">
          {chart.ticks.map((tick, index) => (
            <line
              key={index}
              x1={chart.plot.x}
              x2={chart.plot.x + chart.plot.width}
              y1={tick.y}
              y2={tick.y}
              stroke="currentColor"
              strokeWidth={index === 0 ? 1.5 : 1}
            />
          ))}
        </g>

        <g className="text-muted" fontSize={compact ? 9 : 11} fill="currentColor">
          {chart.ticks.map((tick, index) => (
            <text
              key={`left-${index}`}
              x={chart.plot.x - 8}
              y={tick.y + 3}
              textAnchor="end"
              className="tabular-nums"
            >
              {formatCount(tick.pages)}
            </text>
          ))}
          {/* No right axis when no time was ever recorded (a session the
              client never closed has pages but no seconds): a scale invented
              for a line that is not drawn invites reading the bars off it. */}
          {chart.hasTime
            ? chart.ticks.map((tick, index) => (
                <text
                  key={`right-${index}`}
                  x={chart.plot.x + chart.plot.width + 8}
                  y={tick.y + 3}
                  textAnchor="start"
                  className="tabular-nums"
                >
                  {index === 0 ? "0m" : formatDuration(tick.seconds)}
                </text>
              ))
            : null}
          {chart.xLabels.map((label) => (
            <text
              key={label.date}
              x={label.x}
              y={baseline + 16}
              textAnchor="middle"
            >
              {shortDay(label.date)}
            </text>
          ))}
        </g>

        {/* Series 1 — pages, as bars. */}
        <g className="text-primary">
          {chart.bars.map((bar) =>
            bar.height > 0 ? (
              <rect
                key={bar.date}
                x={bar.x}
                y={bar.y}
                width={bar.width}
                height={bar.height}
                rx={Math.min(2, bar.width / 2)}
                fill="currentColor"
                opacity={0.85}
              />
            ) : null,
          )}
        </g>

        {/* Series 2 — time, as a dashed line with square markers. Weight comes
            from `lineStyleFor`: the bars are the headline metric, and at 90 days
            a full-weight near-white stroke buries them under 90 vertices. */}
        {chart.linePath ? (
          <g className="text-fg" opacity={line.opacity}>
            <path
              d={chart.linePath}
              fill="none"
              stroke="currentColor"
              strokeWidth={line.strokeWidth}
              strokeDasharray="5 4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {line.markers
              ? chart.points.map((point) =>
                  point.seconds > 0 ? (
                    <rect
                      key={point.date}
                      x={point.x - 2.5}
                      y={point.y - 2.5}
                      width={5}
                      height={5}
                      fill="currentColor"
                    />
                  ) : null,
                )
              : null}
          </g>
        ) : null}

        {/* Per-day hit targets. Native tooltips, so no JS popover to keep in sync. */}
        <g>
          {chart.bars.map((bar) => (
            <rect
              key={`hit-${bar.date}`}
              x={bar.centerX - Math.max(bar.width, chart.slot) / 2}
              y={chart.plot.y}
              width={Math.max(bar.width, chart.slot)}
              height={chart.plot.height}
              fill="transparent"
            >
              {/* Unmeasured time is left unsaid — "no time" would claim a
                  measured zero for days whose sessions were simply never
                  closed. */}
              <title>
                {chart.hasTime
                  ? `${longDay(bar.date)} — ${formatCount(bar.pages)} pages, ${formatDurationLong(
                      bar.seconds,
                    )}`
                  : `${longDay(bar.date)} — ${formatCount(bar.pages)} pages`}
              </title>
            </rect>
          ))}
        </g>
      </svg>
    </div>
  );
}
