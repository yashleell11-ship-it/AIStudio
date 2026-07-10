"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BookOpen,
  ChevronRight,
  Clock,
  HardDrive,
  Play,
  TrendingUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { coverUrl } from "@/features/library/api";
import {
  useContinueReading,
  useSeriesList,
  useStatistics,
} from "@/features/library/hooks";
import type { ContinueReadingItem, SeriesSummary } from "@/features/library/types";
import { ApiError } from "@/types/api";
import { cn } from "@/lib/cn";

function StatCard({
  icon: Icon,
  value,
  label,
  accent,
}: {
  icon: React.ComponentType<{ className?: string }>;
  value: string;
  label: string;
  accent: "violet" | "cyan" | "emerald" | "amber";
}) {
  const accentStyles = {
    violet: "from-violet-500/20 to-violet-500/5 text-violet-400",
    cyan: "from-cyan-500/20 to-cyan-500/5 text-cyan-400",
    emerald: "from-emerald-500/20 to-emerald-500/5 text-emerald-400",
    amber: "from-amber-500/20 to-amber-500/5 text-amber-400",
  };

  return (
    <div className="glass-card rounded-xl p-4">
      <div
        className={cn(
          "mb-3 flex size-9 items-center justify-center rounded-lg bg-gradient-to-br",
          accentStyles[accent],
        )}
      >
        <Icon className="size-4" />
      </div>
      <p className="text-2xl font-bold tabular-nums text-fg">{value}</p>
      <p className="mt-0.5 text-xs text-muted">{label}</p>
    </div>
  );
}

function TrendingCard({ series }: { series: SeriesSummary }) {
  return (
    <Link
      href={`/library/${series.id}`}
      className="group shrink-0 snap-start"
    >
      <div className="relative w-[140px] overflow-hidden rounded-xl transition-transform duration-300 group-hover:scale-105 group-hover:shadow-glow">
        <div className="relative aspect-[2/3] w-full bg-surface-2">
          <Image
            src={coverUrl(series.id)}
            alt={series.title}
            fill
            className="object-cover"
            sizes="140px"
            unoptimized
          />
          <div className="absolute inset-0 bg-gradient-to-t from-void/90 via-transparent to-transparent" />
          <p className="absolute inset-x-2 bottom-2 line-clamp-2 text-xs font-medium text-white">
            {series.title}
          </p>
        </div>
      </div>
    </Link>
  );
}

function ContinueReadingCard({ item }: { item: ContinueReadingItem }) {
  return (
    <Link
      href={`/reader/${item.series_id}/${item.chapter_id}?page=${item.last_page}`}
      className="min-w-[280px] shrink-0 snap-start sm:min-w-[320px]"
    >
      <div className="glass-card flex gap-3 rounded-xl p-3 transition-colors hover:border-violet-500/30">
        <div className="relative h-[90px] w-[60px] shrink-0 overflow-hidden rounded-lg bg-surface-2">
          <Image
            src={coverUrl(item.series_id)}
            alt={item.series_title}
            fill
            className="object-cover"
            sizes="60px"
            unoptimized
          />
        </div>
        <div className="flex min-w-0 flex-1 flex-col justify-center">
          <p className="truncate font-medium text-fg">{item.series_title}</p>
          <p className="mt-0.5 truncate text-xs text-muted">{item.chapter_title}</p>
          <div className="mt-2">
            <Progress
              value={item.progress_pct}
              className="h-1 bg-white/10 [&>div]:bg-cyan-500"
              aria-label={`Reading progress for ${item.series_title}`}
            />
          </div>
          <div className="mt-1 flex items-center justify-between text-[10px] text-muted">
            <span>Page {item.last_page}</span>
            <span className="text-cyan-400">{Math.round(item.progress_pct)}%</span>
          </div>
        </div>
      </div>
    </Link>
  );
}

function RecentUpdateRow({ series }: { series: SeriesSummary }) {
  const chapterLabel =
    series.chapter_count > 0
      ? `${series.chapter_count} chapters`
      : "No chapters";

  return (
    <div className="flex items-center gap-3 rounded-xl px-2 py-2 transition-colors hover:bg-white/[0.02]">
      <div className="relative size-12 shrink-0 overflow-hidden rounded-lg bg-surface-2">
        <Image
          src={coverUrl(series.id)}
          alt={series.title}
          fill
          className="object-cover"
          sizes="48px"
          unoptimized
        />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-fg">{series.title}</p>
        <p className="truncate text-xs text-muted">{chapterLabel}</p>
      </div>
      <span className="hidden shrink-0 text-xs text-muted sm:block">
        {new Date(series.updated_at).toLocaleDateString()}
      </span>
      <Link
        href={`/library/${series.id}`}
        className="inline-flex h-8 shrink-0 items-center justify-center rounded-lg bg-violet-600 px-3 text-sm font-medium text-white transition-colors hover:bg-violet-500"
      >
        Read
      </Link>
    </div>
  );
}

function SectionHeader({
  icon: Icon,
  title,
  href,
  linkLabel = "View All",
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  href?: string;
  linkLabel?: string;
}) {
  return (
    <div className="mb-4 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Icon className="size-4 text-cyan-400" aria-hidden />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-fg">
          {title}
        </h2>
      </div>
      {href ? (
        <Link
          href={href}
          className="flex items-center gap-0.5 text-xs text-muted transition-colors hover:text-violet-400"
        >
          {linkLabel}
          <ChevronRight className="size-3.5" />
        </Link>
      ) : null}
    </div>
  );
}

export function DashboardView() {
  const router = useRouter();
  const statsQuery = useStatistics();
  const continueQuery = useContinueReading(6);
  const trendingQuery = useSeriesList({ page: 1, per_page: 6, sort: "updated" });
  const recentQuery = useSeriesList({ page: 1, per_page: 8, sort: "updated" });

  const stats = statsQuery.data;
  const continueItems = continueQuery.data ?? [];
  const trending = trendingQuery.data?.items ?? [];
  const recent = recentQuery.data?.items ?? [];

  const error =
    statsQuery.error instanceof ApiError
      ? statsQuery.error.message
      : trendingQuery.error instanceof ApiError
        ? trendingQuery.error.message
        : null;

  const firstContinue = continueItems[0];

  return (
    <div className="relative min-h-full bg-bg">
      {/* Hero */}
      <section className="relative overflow-hidden px-6 pb-8 pt-10 md:px-10 md:pt-14">
        <div
          className="pointer-events-none absolute inset-0 bg-gradient-to-b from-violet-500/10 via-transparent to-transparent"
          aria-hidden
        />
        <p
          className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 select-none font-display text-[clamp(80px,12vw,180px)] leading-none text-white/[0.03]"
          aria-hidden
        >
          ManhwaManiacs
        </p>
        <div className="relative mx-auto max-w-5xl text-center">
          <h1 className="font-display text-5xl tracking-wide text-fg text-glow md:text-7xl">
            ManhwaManiacs
          </h1>
          <p className="mt-3 text-sm text-muted md:text-base">
            Your Premium Manga &amp; Webtoon Experience
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <Button
              onClick={() => router.push("/library")}
              className="bg-violet-600 hover:bg-violet-500"
            >
              Browse Library
            </Button>
            {firstContinue ? (
              <Button
                variant="secondary"
                onClick={() =>
                  router.push(
                    `/reader/${firstContinue.series_id}/${firstContinue.chapter_id}?page=${firstContinue.last_page}`,
                  )
                }
                className="border border-border/50 bg-white/5 hover:bg-white/10"
              >
                <Play className="size-4 fill-current" />
                Continue Reading
              </Button>
            ) : null}
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-6xl space-y-10 px-6 pb-10 md:px-10">
        {error ? (
          <div className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            {error}
          </div>
        ) : null}

        {/* Trending */}
        <section>
          <SectionHeader icon={TrendingUp} title="Trending Now" href="/library" />
          {trendingQuery.isLoading ? (
            <div className="flex gap-4 overflow-hidden">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="h-[210px] w-[140px] shrink-0 animate-pulse rounded-xl bg-surface-2"
                />
              ))}
            </div>
          ) : trending.length > 0 ? (
            <div className="flex gap-4 overflow-x-auto pb-2 snap-x snap-mandatory scroll-smooth">
              {trending.map((series) => (
                <TrendingCard key={series.id} series={series} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted">Import a library to see trending series.</p>
          )}
        </section>

        {/* Stats */}
        <section>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
            {statsQuery.isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-[108px] animate-pulse rounded-xl bg-surface-2" />
              ))
            ) : stats ? (
              <>
                <StatCard
                  icon={BookOpen}
                  value={stats.total_series.toLocaleString()}
                  label="Total Comics"
                  accent="violet"
                />
                <StatCard
                  icon={Clock}
                  value={stats.total_chapters.toLocaleString()}
                  label="Total Chapters"
                  accent="cyan"
                />
                <StatCard
                  icon={TrendingUp}
                  value={`${stats.reading_streak_days} days`}
                  label="Reading Streak"
                  accent="emerald"
                />
                <StatCard
                  icon={HardDrive}
                  value={stats.total_pages.toLocaleString()}
                  label="Total Pages"
                  accent="amber"
                />
              </>
            ) : null}
          </div>
        </section>

        {/* Continue Reading */}
        {continueQuery.isLoading ? (
          <section aria-busy="true" aria-label="Loading continue reading">
            <SectionHeader icon={Play} title="Continue Reading" />
            <div className="flex gap-3 overflow-hidden">
              {Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className="h-[114px] min-w-[280px] animate-pulse rounded-xl bg-surface-2"
                />
              ))}
            </div>
          </section>
        ) : continueItems.length > 0 ? (
          <section>
            <SectionHeader icon={Play} title="Continue Reading" href="/library" />
            <div className="flex gap-3 overflow-x-auto pb-2 snap-x snap-mandatory scroll-smooth">
              {continueItems.map((item) => (
                <ContinueReadingCard key={item.series_id} item={item} />
              ))}
            </div>
          </section>
        ) : null}

        {/* Recent Updates */}
        <section>
          <SectionHeader icon={Clock} title="Recent Updates" href="/library" />
          {recentQuery.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-16 animate-pulse rounded-xl bg-surface-2" />
              ))}
            </div>
          ) : recent.length > 0 ? (
            <div className="glass-panel divide-y divide-border/30 rounded-xl">
              {recent.map((series) => (
                <RecentUpdateRow key={series.id} series={series} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted">No recent updates yet.</p>
          )}
        </section>
      </div>
    </div>
  );
}
