#!/usr/bin/env python3
"""Time the backend's hot request paths against a REAL database.

The connector probe measures the network. This measures everything after it:
the library list, series detail, the reader manifest, progress writes, the
statistics screen, and the novel chapter path — the six things the owner waits
on that never leave the VPS.

Two things make a number here trustworthy:

* **A copy of the production database.** Row counts, index selectivity and
  page-cache behaviour are properties of the real data; a fixture DB measures
  a fixture. The copy is made inside the container and the original is opened
  read-only, so a benchmark can never write to production.
* **Statement capture.** Every path records the SQL it issued, so the report
  can say "42 statements" as well as "31 ms". An N+1 is invisible in a
  latency number until the row count grows, and by then it is a bug report.
  ``--explain`` runs EXPLAIN QUERY PLAN over the captured statements and
  flags the ones SQLite answers with a SCAN.

``--seed N`` clones the profile's library up to N series (and its progress and
sessions in proportion) in the *copy*, which is how a path that is fine at 2
series and quadratic at 300 gets caught before the owner finds it.

Usage:
    ./.venv/bin/python scripts/bench_hot_paths.py --remote
    ./.venv/bin/python scripts/bench_hot_paths.py --remote --seed 300 --explain
    ./.venv/bin/python scripts/bench_hot_paths.py --db /tmp/copy.db --iterations 50
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_OVERLAY = os.environ.get("MM_PROBE_OVERLAY", "")
if _OVERLAY and Path(_OVERLAY).is_dir():
    sys.path.insert(0, _OVERLAY)

VPS_HOST = os.environ.get("MM_VPS_HOST", "ubuntu@135.148.43.147")
VPS_CONTAINER = os.environ.get("MM_VPS_CONTAINER", "manhwamaniacs-backend")
PROD_DB = os.environ.get("MM_PROD_DB", "/data/manhwamaniacs.db")


# --- statement capture ------------------------------------------------------


class Recorder:
    """Collect every SQL statement the engine executes, in order."""

    def __init__(self) -> None:
        self.statements: list[str] = []
        self.enabled = False

    def install(self, engine) -> None:
        from sqlalchemy import event

        @event.listens_for(engine, "before_cursor_execute")
        def _capture(conn, cursor, statement, parameters, context, executemany):
            if self.enabled:
                self.statements.append(statement)

    def __enter__(self) -> "Recorder":
        self.statements = []
        self.enabled = True
        return self

    def __exit__(self, *exc) -> None:
        self.enabled = False


def _norm(sql: str) -> str:
    return " ".join(sql.split())


# --- the paths --------------------------------------------------------------


def build_cases(db, ctx, args):
    """(name, callable) for each hot path, bound to a live Session."""
    from core.content_rating import resolve_mature_gate
    from services.browse_service import BrowseService
    from services.followed_series_service import FollowedSeriesService
    from services.novel_service import NovelService
    from services.progress_service import ProgressInput, ProgressService
    from services.reader_service import ReaderService
    from services.source_cache_service import SourceCacheService

    user_id, profile_id = ctx["user_id"], ctx["profile_id"]

    def browse():
        return BrowseService(
            mature_enabled=resolve_mature_gate(db, profile_id, user_id),
            db=db,
            user_id=user_id,
            profile_id=profile_id,
        )

    def followed():
        return FollowedSeriesService(
            db, browse(), user_id=user_id, profile_id=profile_id
        )

    cases: list[tuple[str, object]] = [
        ("library.list(40)", lambda: followed().list_series(page=1, per_page=40)),
        ("library.list(200)", lambda: followed().list_series(page=1, per_page=200)),
        ("library.continue_reading", lambda: followed().continue_reading(limit=10)),
        ("library.recently_updated", lambda: followed().recently_updated(limit=10)),
        ("library.statistics(30d)", lambda: followed().statistics(days=30)),
        ("library.statistics(365d)", lambda: followed().statistics(days=365)),
        ("progress.continue_reading", lambda: ProgressService(
            db, user_id=user_id, profile_id=profile_id).continue_reading(limit=20)),
        ("progress.history", lambda: ProgressService(
            db, user_id=user_id, profile_id=profile_id).reading_history(limit=50)),
    ]

    followed_id = ctx.get("followed_id")
    if followed_id:
        cases.append(
            ("library.detail", lambda: followed().get_detail(followed_id))
        )

    series = ctx.get("series")  # (source_id, series_key, chapter_key)
    if series:
        source_id, series_key, chapter_key = series
        cases.append(
            ("source_cache.chapter_list", lambda: SourceCacheService(
                db, browse()).get_chapter_list(source_id, series_key))
        )
        if chapter_key:
            cases.append(
                ("reader.manifest", lambda: ReaderService(
                    browse(), db=db, user_id=user_id, profile_id=profile_id
                ).manifest(source_id, series_key, chapter_key))
            )

    novel = ctx.get("novel")  # (source_id, series_key, chapter_key)
    if novel:
        n_source, n_series, n_chapter = novel
        cases.append(
            ("novels.chapter(cached)", lambda: NovelService(
                db, browse(), SourceCacheService(db, browse())
            ).get_chapter(n_source, n_series, n_chapter))
        )

    if series and not args.read_only:
        source_id, series_key, chapter_key = series

        def progress_one(counter=[0]):
            counter[0] += 1
            svc = ProgressService(db, user_id=user_id, profile_id=profile_id)
            return svc.save_one(ProgressInput(
                source_id=source_id,
                series_key=series_key,
                chapter_key=chapter_key or "bench-chapter",
                last_page=counter[0] % 40 + 1,
                page_count=60,
                time_spent_seconds=counter[0],
            ))

        def progress_batch(counter=[0]):
            counter[0] += 1
            svc = ProgressService(db, user_id=user_id, profile_id=profile_id)
            base = counter[0] * 100
            return svc.save_batch([
                ProgressInput(
                    source_id=source_id,
                    series_key=series_key,
                    chapter_key=f"bench-batch-{i}",
                    last_page=(base + i) % 40 + 1,
                    page_count=60,
                    time_spent_seconds=base + i,
                )
                for i in range(args.batch_size)
            ])

        cases.append(("progress.save_one", progress_one))
        cases.append((f"progress.save_batch({args.batch_size})", progress_batch))

    return cases


def discover_context(db, args) -> dict:
    """Pick a real user/profile/series to benchmark against."""
    from sqlalchemy import select

    from database.models import (
        ChapterProgress,
        FollowedSeries,
        NovelChapterCache,
        ReadingProfile,
        SourceSeriesCache,
        User,
    )

    user = db.execute(select(User).order_by(User.id)).scalars().first()
    if user is None:
        raise SystemExit("no users in this database; nothing to benchmark")
    profile = db.execute(
        select(ReadingProfile).where(ReadingProfile.user_id == user.id)
        .order_by(ReadingProfile.id)
    ).scalars().first()
    ctx: dict = {
        "user_id": user.id,
        "profile_id": profile.id if profile is not None else None,
    }

    follow = db.execute(
        select(FollowedSeries)
        .where(FollowedSeries.user_id == user.id)
        .order_by(FollowedSeries.id)
    ).scalars().first()
    if follow is not None:
        ctx["followed_id"] = follow.id
        chapter_key = None
        prog = db.execute(
            select(ChapterProgress).where(
                ChapterProgress.source_id == follow.source_id,
                ChapterProgress.series_key == follow.series_key,
            )
        ).scalars().first()
        if prog is not None:
            chapter_key = prog.chapter_key
        else:
            row = db.get(SourceSeriesCache, (follow.source_id, follow.series_key))
            if row is not None and row.chapters:
                try:
                    chapters = json.loads(row.chapters)
                    if chapters:
                        chapter_key = chapters[0].get("key") or chapters[0].get("id")
                except (TypeError, ValueError):
                    pass
        ctx["series"] = (follow.source_id, follow.series_key, chapter_key)

    novel_row = db.execute(select(NovelChapterCache)).scalars().first()
    if novel_row is not None:
        ctx["novel"] = (
            novel_row.source_id, novel_row.series_key, novel_row.chapter_key
        )
    return ctx


def seed(db, ctx, target: int) -> None:
    """Clone the profile's library up to ``target`` series in the COPY.

    Each clone carries a chapter list and a handful of progress + session rows
    so the paths that join across them see a realistic shape, not a library of
    empty shells.
    """
    from datetime import timedelta

    from sqlalchemy import func, select

    from core.time_utils import utcnow
    from database.models import (
        ChapterProgress,
        FollowedSeries,
        ReadingSession,
        SourceSeriesCache,
    )

    user_id, profile_id = ctx["user_id"], ctx["profile_id"]
    existing = db.execute(
        select(func.count()).select_from(FollowedSeries)
        .where(FollowedSeries.user_id == user_id)
    ).scalar_one()
    if existing >= target:
        print(f"seed: already {existing} follows, target {target} — nothing to do")
        return
    template = db.execute(
        select(FollowedSeries).where(FollowedSeries.user_id == user_id)
    ).scalars().first()
    if template is None:
        raise SystemExit("seed: no followed series to clone")
    tmpl_cache = db.get(
        SourceSeriesCache, (template.source_id, template.series_key)
    )
    now = utcnow()
    for i in range(existing, target):
        key = f"{template.series_key}--bench-{i}"
        db.add(FollowedSeries(
            user_id=user_id,
            profile_id=profile_id,
            source_id=template.source_id,
            series_key=key,
            title=f"{template.title} Bench {i}",
            cover_url=template.cover_url,
            content_rating=template.content_rating,
            known_chapters=template.known_chapters,
            chapter_count=template.chapter_count,
            reading_status=("reading" if i % 3 else "completed"),
            is_favorite=(i % 7 == 0),
            sort_order=i,
        ))
        if tmpl_cache is not None:
            db.add(SourceSeriesCache(
                source_id=template.source_id,
                series_key=key,
                title=tmpl_cache.title,
                cover_url=tmpl_cache.cover_url,
                description=tmpl_cache.description,
                genres=tmpl_cache.genres,
                author=tmpl_cache.author,
                status=tmpl_cache.status,
                chapters=tmpl_cache.chapters,
                fetched_at=tmpl_cache.fetched_at,
            ))
        for c in range(3):
            read_at = now - timedelta(days=(i % 40), hours=c)
            db.add(ChapterProgress(
                user_id=user_id,
                profile_id=profile_id,
                source_id=template.source_id,
                series_key=key,
                chapter_key=f"bench-ch-{c}",
                chapter_number=float(c + 1),
                last_page=20,
                page_count=20,
                is_completed=True,
                started_at=read_at,
                last_read_at=read_at,
                completed_at=read_at,
                time_spent_seconds=300,
            ))
            db.add(ReadingSession(
                user_id=user_id,
                profile_id=profile_id,
                source_id=template.source_id,
                series_key=key,
                chapter_key=f"bench-ch-{c}",
                chapter_number=float(c + 1),
                start_page=1,
                end_page=20,
                pages_read=20,
                started_at=read_at,
                ended_at=read_at + timedelta(minutes=5),
                duration_seconds=300,
            ))
        if i % 200 == 0:
            db.commit()
    db.commit()
    print(f"seed: library grown {existing} -> {target} series")


# --- runner -----------------------------------------------------------------


def run(args) -> int:
    db_path = args.db
    if not db_path:
        src = Path(PROD_DB)
        if not src.exists():
            raise SystemExit(f"no database at {src}; pass --db")
        db_path = "/tmp/mm_bench.db"
        # Copy through SQLite's own backup so an in-flight WAL is included and
        # the production file is never opened for writing.
        import sqlite3

        Path(db_path).unlink(missing_ok=True)
        source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        dest = sqlite3.connect(db_path)
        source.backup(dest)
        dest.close()
        source.close()
        print(f"benchmarking a copy of {src} at {db_path}")

    os.environ["MM_DB_PATH"] = db_path
    from core.config import get_settings

    get_settings.cache_clear()
    from database.session import SessionLocal, get_engine

    recorder = Recorder()
    recorder.install(get_engine())

    db = SessionLocal()
    ctx = discover_context(db, args)
    print(f"context: {ctx}")
    if args.seed:
        seed(db, ctx, args.seed)
        db.expire_all()

    cases = build_cases(db, ctx, args)
    report: list[dict] = []
    for name, fn in cases:
        try:
            fn()  # warm: first call fills the connector/registry caches
        except Exception as exc:  # noqa: BLE001
            print(f"{name:34} SKIP  {type(exc).__name__}: {exc}"[:150])
            continue
        with recorder:
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass
        stmts = list(recorder.statements)
        samples: list[float] = []
        for _ in range(args.iterations):
            t0 = time.perf_counter()
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                print(f"{name:34} FAIL  {type(exc).__name__}: {exc}"[:150])
                samples = []
                break
            samples.append((time.perf_counter() - t0) * 1000.0)
        if not samples:
            continue
        samples.sort()
        report.append({
            "name": name,
            "median_ms": round(statistics.median(samples), 3),
            "p95_ms": round(samples[min(len(samples) - 1, int(len(samples) * 0.95))], 3),
            "max_ms": round(samples[-1], 3),
            "statements": len(stmts),
            "distinct_statements": len({_norm(s) for s in stmts}),
            "sql": [_norm(s) for s in stmts] if args.dump_sql else [],
        })

    print()
    print(f"{'path':34} {'median':>9} {'p95':>9} {'max':>9} {'stmts':>6} {'uniq':>5}")
    print("-" * 78)
    for r in report:
        print(f"{r['name']:34} {r['median_ms']:>8.2f}m {r['p95_ms']:>8.2f}m "
              f"{r['max_ms']:>8.2f}m {r['statements']:>6} {r['distinct_statements']:>5}")

    if args.explain:
        print("\n=== EXPLAIN QUERY PLAN (statements answered with a SCAN) ===")
        seen: set[str] = set()
        conn = get_engine().raw_connection()
        cur = conn.cursor()
        for r in report:
            for sql in r["sql"] or []:
                if not sql.lower().startswith("select") or sql in seen:
                    continue
                seen.add(sql)
                try:
                    plan = cur.execute(
                        "EXPLAIN QUERY PLAN " + sql,
                        _dummy_params(sql),
                    ).fetchall()
                except Exception:  # noqa: BLE001
                    continue
                lines = [row[-1] for row in plan]
                if any("SCAN" in ln for ln in lines):
                    print(f"\n[{r['name']}] {sql[:170]}")
                    for ln in lines:
                        print(f"    {ln}")
        cur.close()
        conn.close()

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({
            "db": db_path,
            "seeded": args.seed,
            "iterations": args.iterations,
            "context": {k: list(v) if isinstance(v, tuple) else v
                        for k, v in ctx.items()},
            "results": report,
        }, indent=2), encoding="utf-8")
        print(f"\nWrote {args.out}")
    db.close()
    return 0


def _dummy_params(sql: str):
    """Bind placeholders so EXPLAIN can prepare the statement."""
    return tuple([None] * sql.count("?"))


def _run_remote(argv: list[str], out: str, sync_code: bool) -> int:
    script = Path(__file__).resolve()
    host_tmp = "/tmp/bench_hot_paths.py"
    ctr_out = "/tmp/bench_results.json"
    overlay = ""
    if sync_code:
        from scripts.e2e_connector_check import _sync_code_to_container

        overlay = _sync_code_to_container()
    inner = " ".join(shlex.quote(a) for a in (list(argv) + ["--out", ctr_out]))
    subprocess.run(
        ["scp", "-o", "BatchMode=yes", str(script), f"{VPS_HOST}:{host_tmp}"],
        check=True,
    )
    remote_cmd = (
        f"set -e; docker exec {VPS_CONTAINER} mkdir -p /app/scripts; "
        f"docker cp {host_tmp} {VPS_CONTAINER}:/app/scripts/_bench.py; "
        f"docker exec -w /app "
        + (f"-e MM_PROBE_OVERLAY={overlay} " if overlay else "")
        + f"{VPS_CONTAINER} python /app/scripts/_bench.py {inner}; "
        f"rc=$?; docker exec {VPS_CONTAINER} rm -f /app/scripts/_bench.py; "
        f"docker cp {VPS_CONTAINER}:{ctr_out} {host_tmp}.out.json 2>/dev/null || true; "
        f"exit $rc"
    )
    rc = subprocess.run(["ssh", "-o", "BatchMode=yes", VPS_HOST, remote_cmd]).returncode
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        if subprocess.run(
            ["scp", "-o", "BatchMode=yes", f"{VPS_HOST}:{host_tmp}.out.json", out]
        ).returncode == 0:
            print(f"==> pulled {out}")
    return rc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="", help="database to benchmark (default: a copy of prod)")
    ap.add_argument("--iterations", type=int, default=25)
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0,
                    help="grow the library to N series in the COPY before timing")
    ap.add_argument("--explain", action="store_true",
                    help="EXPLAIN QUERY PLAN the captured statements")
    ap.add_argument("--dump-sql", action="store_true", default=True)
    ap.add_argument("--read-only", action="store_true",
                    help="skip the write paths (progress saves)")
    ap.add_argument("--out", default="")
    ap.add_argument("--remote", action="store_true",
                    help="run inside the production container over ssh")
    ap.add_argument("--sync-code", action="store_true",
                    help="with --remote: overlay the working tree's services/")
    args = ap.parse_args()

    if args.remote:
        passthrough: list[str] = []
        skip_next = False
        for a in sys.argv[1:]:
            if skip_next:
                skip_next = False
                continue
            if a in ("--remote", "--sync-code"):
                continue
            if a == "--out":
                skip_next = True
                continue
            if a.startswith("--out="):
                continue
            passthrough.append(a)
        raise SystemExit(_run_remote(passthrough, args.out, args.sync_code))

    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
