#!/usr/bin/env python
"""Measure a bulk chapter window against the same chapters fetched one by one.

Run it on the VPS, inside the backend container, because that is the egress
whose latency and blocks are the point:

    docker exec manhwamaniacs-backend python scripts/bench_bulk_window.py \
        discover --kind manga --source asurascans --count 10
    docker exec manhwamaniacs-backend python scripts/bench_bulk_window.py \
        run --kind manga --source asurascans --series <key> --mode single --keys-file /tmp/k.json
    docker exec ... --mode bulk ...

Two rules make the numbers mean something:

* **One mode per process.** Connectors keep a 180-second in-process cache, so a
  second mode in the same interpreter would measure that cache, not the source.
* **A throwaway SQLite per run.** ``source_series_cache`` would otherwise carry
  the first run's series page into the second and hand it a head start the real
  first-open never gets.

Nothing here writes to the deployment's database or its caches.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from database.models import Base  # noqa: E402
from services.browse_service import BrowseService  # noqa: E402
from services.novel_service import NovelService  # noqa: E402
from services.reader_service import ReaderService  # noqa: E402
from services.source_cache_service import SourceCacheService  # noqa: E402


def _session(db_path: str):
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def _services(db_path: str):
    session = _session(db_path)
    browse = BrowseService(mature_enabled=True, db=session)
    reader = ReaderService(browse, db=session)
    novels = NovelService(session, browse, SourceCacheService(session, browse))
    return browse, reader, novels


def discover(args: argparse.Namespace) -> int:
    """Pick a real series on ``--source`` with at least ``--count`` chapters."""
    browse, _, _ = _services(args.db)
    listing = browse.list_series(args.source, page=1)
    candidates = [item["id"] for item in listing.get("items", [])]
    for series_key in candidates[: args.scan]:
        try:
            chapters = browse.get_chapters(args.source, series_key)
        except Exception as exc:  # noqa: BLE001 - just skip a bad series
            print(f"  skip {series_key}: {exc}", file=sys.stderr)
            continue
        if len(chapters) < args.count:
            continue
        # Oldest chapters first: newest-first is how the lists arrive, and a
        # Read-all window walks forward from chapter 1.
        keys = [c["id"] for c in chapters][-args.count :]
        print(json.dumps({"series_key": series_key, "chapter_keys": keys}, indent=2))
        return 0
    print(f"no series on {args.source} had >= {args.count} chapters", file=sys.stderr)
    return 1


def run(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.keys_file).read_text())
    series_key = payload["series_key"]
    keys = payload["chapter_keys"][: args.count]
    _, reader, novels = _services(args.db)

    if args.warm:
        # The steady state, and the one worth measuring separately: the reader
        # just looked at the series page, so source_series_cache already holds
        # the chapter list and NO mode pays the series fetch. What is left is
        # only the genuinely per-chapter work.
        SourceCacheService(
            _session(args.db), BrowseService(mature_enabled=True)
        ).get_chapter_list(args.source, series_key)

    per_item: list[dict[str, object]] = []
    started = time.perf_counter()
    if args.mode == "parallel-single":
        # What a client that PIPELINES the existing single endpoint costs the
        # server: N concurrent requests, each with its own session and its own
        # service instances, exactly as FastAPI would build them. The point of
        # measuring it is that each one resolves the chapter list for itself.
        from concurrent.futures import ThreadPoolExecutor

        def one(index_key: tuple[int, str]) -> dict[str, object]:
            index, key = index_key
            # A warm run shares one cache file, because in production the
            # concurrent requests share one database; a cold run gives each its
            # own, because that is what "ten readers' first open, nothing
            # cached" actually costs.
            own_db = args.db if args.warm else f"{args.db}.{index}"
            _, own_reader, own_novels = _services(own_db)
            item_started = time.perf_counter()
            status = "ok"
            try:
                if args.kind == "manga":
                    own_reader.manifest(args.source, series_key, key)
                else:
                    own_novels.get_chapter(args.source, series_key, key)
            except Exception as exc:  # noqa: BLE001 - a failure is a data point
                status = f"{type(exc).__name__}: {exc}"[:120]
            return {
                "chapter_key": key,
                "status": status,
                "ms": round((time.perf_counter() - item_started) * 1000, 1),
            }

        with ThreadPoolExecutor(max_workers=len(keys)) as pool:
            per_item = list(pool.map(one, list(enumerate(keys))))
    elif args.mode == "single":
        for key in keys:
            item_started = time.perf_counter()
            status = "ok"
            try:
                if args.kind == "manga":
                    reader.manifest(args.source, series_key, key)
                else:
                    novels.get_chapter(args.source, series_key, key)
            except Exception as exc:  # noqa: BLE001 - a failure is a data point
                status = f"{type(exc).__name__}: {exc}"[:120]
            per_item.append(
                {
                    "chapter_key": key,
                    "status": status,
                    "ms": round((time.perf_counter() - item_started) * 1000, 1),
                }
            )
    else:
        if args.kind == "manga":
            window = reader.manifest_batch(args.source, series_key, keys)
        else:
            window = novels.get_chapters_bulk(args.source, series_key, keys)
        per_item = [
            {
                "chapter_key": item["chapter_key"],
                "status": item["status"]
                if item["status"] == "ok"
                else json.dumps(item["error"]),
            }
            for item in window["items"]
        ]
    total_ms = round((time.perf_counter() - started) * 1000, 1)

    print(
        json.dumps(
            {
                "kind": args.kind,
                "source": args.source,
                "mode": args.mode,
                "chapters": len(keys),
                "concurrency": os.getenv("MM_BULK_FETCH_CONCURRENCY", "default(4)"),
                "total_ms": total_ms,
                "ok": sum(1 for i in per_item if i["status"] == "ok"),
                "items": per_item,
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--kind", choices=("manga", "novel"), default="manga")
        p.add_argument("--source", required=True)
        p.add_argument("--count", type=int, default=10)
        p.add_argument("--db", default="/tmp/bench-bulk.db")
        p.add_argument(
            "--warm",
            action="store_true",
            help="pre-resolve the chapter list into the cache before timing",
        )

    d = sub.add_parser("discover")
    common(d)
    d.add_argument("--scan", type=int, default=8, help="series to try before giving up")
    d.set_defaults(func=discover)

    r = sub.add_parser("run")
    common(r)
    r.add_argument(
        "--mode", choices=("single", "parallel-single", "bulk"), required=True
    )
    r.add_argument("--keys-file", required=True)
    r.set_defaults(func=run)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
