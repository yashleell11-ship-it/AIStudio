#!/usr/bin/env python3
"""Live end-to-end connector check.

For every registered connector, exercise the full read path a user hits:

    browse  -> get_series_list(1)
    detail  -> get_series(first.id)
    chapters-> get_chapters(first.id)          ("chapters inside the series")
    pages   -> get_chapter_pages(first chapter) ("pages inside the chapter")
    images  -> find_page(page.id) + fetch the bytes the image proxy would serve

The ``images`` stage is the one that separates "the site still lists things"
from "a reader can actually read it": a source whose page CDN 404s, hotlinks
behind a Referer we do not send, or answers with a redirect the proxy refuses
to follow is *broken*, even though every earlier stage passes. It runs the
real production code path (``BrowseService._fetch_url`` — SSRF allowlist,
``fetch_proxied_image`` hook, connector ``image_fetch_headers``, no redirect
following) so a PASS here means the deployed reader works.

Run this ON THE VPS, not on a laptop: sources are gated on egress IP
reputation, and a residential IP reports sources as live that are dead in
production. See ``--remote`` for the one-liner that does it.

Records a per-stage PASS/FAIL + timing + error so we can print a tick-mark
table of what actually works live. Runs connectors concurrently with a hard
per-connector timeout so dead/slow sites never hang the run.

Usage:
    ./.venv/bin/python scripts/e2e_connector_check.py            # all browsable
    ./.venv/bin/python scripts/e2e_connector_check.py --mature   # include mature
    ./.venv/bin/python scripts/e2e_connector_check.py --only id1,id2
    ./.venv/bin/python scripts/e2e_connector_check.py --workers 8 --timeout 30
    ./.venv/bin/python scripts/e2e_connector_check.py --no-images  # skip byte fetch

    # from the laptop, executed inside the production container:
    ./.venv/bin/python scripts/e2e_connector_check.py --remote
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# When --sync-code ships the working tree's connectors/ into the container,
# they land in an overlay dir that must win over the image's baked-in copy.
# Prepending here (before the first `connectors` import) is what makes a
# remote run exercise the fix rather than what is currently deployed.
_OVERLAY = os.environ.get("MM_PROBE_OVERLAY", "")
if _OVERLAY and Path(_OVERLAY).is_dir():
    sys.path.insert(0, _OVERLAY)

from connectors.registry import create_connector, list_installed_connectors  # noqa: E402

# Reported stages, in the order a reader hits them. ``search`` is reported and
# timed but deliberately kept out of READ_STAGES: a source whose search is
# broken is still readable by browsing, and conflating the two would flip
# perfectly good sources to PARTIAL.
STAGES = ("browse", "search", "detail", "chapters", "pages", "images")
READ_STAGES = ("browse", "detail", "chapters", "pages", "images")

# Latency budgets (seconds) for the summary table. The owner's complaint is
# "make everything fast", so a stage that PASSes slowly is still a finding.
SLOW_STAGE_SECS = 3.0
SLOW_TOTAL_SECS = 8.0

VPS_HOST = os.environ.get("MM_VPS_HOST", "ubuntu@135.148.43.147")
VPS_CONTAINER = os.environ.get("MM_VPS_CONTAINER", "manhwamaniacs-backend")


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\'-]{3,}")


def _search_term(title: str) -> str:
    """Pick a query that the source itself should be able to find.

    Searching for a word lifted from a title the source just returned tests
    the search *path* rather than the site's catalog coverage: a generic term
    legitimately returns 0 hits on a small source and would read as a bug.
    """
    for word in _WORD_RE.findall(title or ""):
        low = word.lower()
        if low in {"the", "and", "with", "from", "that", "this", "comic", "manga"}:
            continue
        return word
    return "love"


def _first_id(items) -> str | None:
    for it in items:
        sid = getattr(it, "id", None)
        if sid:
            return sid
    return None


# --- image bytes -----------------------------------------------------------
# Reuse the *production* fetch verbatim rather than reimplementing it: the
# allowlist, the Referer headers and the refuse-to-follow-redirects rule are
# exactly the things that decide whether a page renders for a real user, so a
# hand-rolled copy here would drift and lie. BrowseService.__new__ skips
# __init__ (no DB/profile needed) — _fetch_url only touches module-level
# helpers via self.
def _image_fetcher():
    from services.browse_service import BrowseService

    svc = BrowseService.__new__(BrowseService)
    return lambda url, connector: BrowseService._fetch_url(svc, url, connector)


def _sample_indices(n: int, want: int) -> list[int]:
    """First / middle / last page indices — a chapter often rots unevenly."""
    if n <= want:
        return list(range(n))
    if want <= 1:
        return [0]
    step = (n - 1) / (want - 1)
    return sorted({int(round(i * step)) for i in range(want)})


def check_images(conn, pages, samples: int) -> tuple[str, int, int, str, float, float]:
    """Fetch real bytes for a few pages the way the image proxy would.

    Returns (status, n_ok, n_tried, error, find_page_secs, fetch_secs). The
    two timings are split because they fail and drag differently: a slow
    ``find_page`` means the connector refetches the chapter document on every
    single image (an N+1 the reader pays once per page), while a slow byte
    fetch is the CDN.

    Also exercises ``find_page``, which the reader route uses to resolve a
    page id back to a Page — a connector can list pages fine and still serve
    nothing if that is broken.
    """
    if not pages:
        return "-", 0, 0, "", 0.0, 0.0
    try:
        fetch = _image_fetcher()
    except Exception as exc:  # noqa: BLE001
        return "ERROR", 0, 0, f"image harness: {type(exc).__name__}: {exc}"[:200], 0.0, 0.0

    idxs = _sample_indices(len(pages), samples)
    n_ok = 0
    n_tried = 0
    first_error = ""
    t_find = 0.0
    t_fetch = 0.0
    for i in idxs:
        page = pages[i]
        n_tried += 1
        try:
            # production resolves id -> Page before fetching; verify that too
            t_fp = time.monotonic()
            resolved = conn.find_page(page.id)
            t_find += time.monotonic() - t_fp
            if resolved is None or not getattr(resolved, "remote_url", None):
                first_error = first_error or f"find_page({page.id})-> none/no url"
                continue
            t_img = time.monotonic()
            media_type, data = fetch(resolved.remote_url, conn)
            t_fetch += time.monotonic() - t_img
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
            # AppError carries the upstream status in .details
            extra = getattr(exc, "details", None)
            if isinstance(extra, dict) and extra.get("reason"):
                detail = f"{detail} [{extra['reason']}]"
            first_error = first_error or f"p{i}: {detail}"[:200]
            continue
        if not data:
            first_error = first_error or f"p{i}: empty body"
            continue
        if not media_type.startswith("image/"):
            first_error = first_error or f"p{i}: content-type {media_type}"
            continue
        n_ok += 1

    if n_ok == n_tried and n_tried:
        return "PASS", n_ok, n_tried, "", t_find, t_fetch
    if n_ok:
        return "PARTIAL", n_ok, n_tried, first_error, t_find, t_fetch
    return "FAIL", n_ok, n_tried, first_error or "no image bytes", t_find, t_fetch


def check_one(source_type: str, *, images: bool = True, image_samples: int = 3,
              search: bool = True, budget: float = 0.0) -> dict:
    """Probe one connector, spending at most ``budget`` seconds (0 = unlimited).

    The budget is checked at stage boundaries rather than enforced by killing
    a thread, because a Python thread blocked in a socket read cannot be
    cancelled. That is enough: the underlying client already caps a single
    request, so the worst overrun is one in-flight request past the line.
    """
    result = {
        "source_id": source_type,
        "browse": "-",
        "search": "-",
        "detail": "-",
        "chapters": "-",
        "pages": "-",
        "images": "-",
        "series_sample": "",
        "search_term": "",
        "n_series": 0,
        "n_search": 0,
        "n_chapters": 0,
        "n_pages": 0,
        "n_images_ok": 0,
        "n_images_tried": 0,
        "error": "",
        "ok": False,
        "secs": 0.0,
        # Per-stage wall clock in seconds. This is the half of the audit the
        # PASS/FAIL grid cannot express: a source that returns the right bytes
        # in nine seconds is a source the owner experiences as broken.
        "t": {s: 0.0 for s in STAGES},
        "t_find_page": 0.0,
    }
    t0 = time.monotonic()
    deadline = (t0 + budget) if budget > 0 else float("inf")

    def _out_of_time() -> bool:
        return time.monotonic() >= deadline

    try:
        conn = create_connector(source_type)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"create: {type(exc).__name__}: {exc}"[:200]
        result["secs"] = round(time.monotonic() - t0, 1)
        return result

    # browse
    t_stage = time.monotonic()
    try:
        listing = conn.get_series_list(1)
        items = list(getattr(listing, "items", []) or [])
        result["t"]["browse"] = round(time.monotonic() - t_stage, 2)
        result["n_series"] = len(items)
        if not items:
            result["browse"] = "FAIL"
            result["error"] = "browse returned 0 series"
            result["secs"] = round(time.monotonic() - t0, 1)
            return result
        result["browse"] = "PASS"
        first = items[0]
        result["series_sample"] = (getattr(first, "title", "") or "")[:48]
    except Exception as exc:  # noqa: BLE001
        result["t"]["browse"] = round(time.monotonic() - t_stage, 2)
        result["browse"] = "FAIL"
        result["error"] = f"browse: {type(exc).__name__}: {exc}"[:200]
        result["secs"] = round(time.monotonic() - t0, 1)
        return result

    # search — timed and reported, but never gates ``ok`` (see STAGES).
    if search and not _out_of_time():
        term = _search_term(result["series_sample"])
        result["search_term"] = term
        t_stage = time.monotonic()
        try:
            found = conn.search_series(term, 1)
            hits = list(getattr(found, "items", []) or [])
            result["t"]["search"] = round(time.monotonic() - t_stage, 2)
            result["n_search"] = len(hits)
            result["search"] = "PASS" if hits else "FAIL"
        except NotImplementedError:
            result["t"]["search"] = round(time.monotonic() - t_stage, 2)
            result["search"] = "-"
        except Exception as exc:  # noqa: BLE001
            result["t"]["search"] = round(time.monotonic() - t_stage, 2)
            result["search"] = "FAIL"
            result["search_error"] = f"{type(exc).__name__}: {exc}"[:160]

    # Walk detail->chapters->pages for up to a few browsed series: a single
    # title can be a source-data anomaly (e.g. a licensed/delisted series with
    # no readable chapters), so try the next series before declaring failure.
    # We keep the best (deepest-reaching) attempt.
    candidate_ids = [sid for sid in (_first_id([it]) for it in items[:5]) if sid]
    best = {"detail": "FAIL", "chapters": "FAIL", "pages": "-", "images": "-",
            "n_chapters": 0, "n_pages": 0, "n_images_ok": 0, "n_images_tried": 0,
            "sample": result["series_sample"], "error": "", "depth": -1,
            "t_detail": 0.0, "t_chapters": 0.0, "t_pages": 0.0, "t_images": 0.0,
            "t_find_page": 0.0}

    def _depth(d: dict) -> int:
        score = 0
        if d["detail"] == "PASS":
            score = 1
        if d["chapters"] == "PASS":
            score = 2
        if d["pages"] == "PASS":
            score = 3
        if d["images"] == "PARTIAL":
            score = 4
        if d["images"] == "PASS":
            score = 5
        return score

    target_depth = 5 if images else 3

    for series_id in candidate_ids:
        if _out_of_time():
            best["error"] = best["error"] or f"budget {budget:.0f}s exhausted"
            break
        attempt = {"detail": "FAIL", "chapters": "FAIL", "pages": "-", "images": "-",
                   "n_chapters": 0, "n_pages": 0, "n_images_ok": 0, "n_images_tried": 0,
                   "sample": result["series_sample"], "error": "", "depth": -1,
                   "t_detail": 0.0, "t_chapters": 0.0, "t_pages": 0.0, "t_images": 0.0,
                   "t_find_page": 0.0}
        chapter_id = None
        t_stage = time.monotonic()
        try:
            series = conn.get_series(series_id)
            attempt["t_detail"] = round(time.monotonic() - t_stage, 2)
            attempt["detail"] = "PASS" if series is not None else "FAIL"
            if series is None:
                attempt["error"] = "detail returned None"
            elif getattr(series, "title", None):
                attempt["sample"] = series.title[:48]
        except Exception as exc:  # noqa: BLE001
            attempt["t_detail"] = round(time.monotonic() - t_stage, 2)
            attempt["error"] = f"detail: {type(exc).__name__}: {exc}"[:200]
        t_stage = time.monotonic()
        try:
            chapters = list(conn.get_chapters(series_id) or [])
            attempt["t_chapters"] = round(time.monotonic() - t_stage, 2)
            attempt["n_chapters"] = len(chapters)
            attempt["chapters"] = "PASS" if chapters else "FAIL"
            if not chapters and not attempt["error"]:
                attempt["error"] = "0 chapters"
            if chapters:
                chapter_id = getattr(chapters[0], "id", None)
        except Exception as exc:  # noqa: BLE001
            attempt["t_chapters"] = round(time.monotonic() - t_stage, 2)
            attempt["error"] = attempt["error"] or f"chapters: {type(exc).__name__}: {exc}"[:200]
        if chapter_id is not None:
            page_list: list = []
            t_stage = time.monotonic()
            try:
                page_list = list(conn.get_chapter_pages(chapter_id) or [])
                attempt["t_pages"] = round(time.monotonic() - t_stage, 2)
                attempt["n_pages"] = len(page_list)
                has_url = bool(page_list) and bool(getattr(page_list[0], "remote_url", None))
                attempt["pages"] = "PASS" if has_url else "FAIL"
                if not has_url and not attempt["error"]:
                    attempt["error"] = "0 pages / no image url"
            except Exception as exc:  # noqa: BLE001
                attempt["t_pages"] = round(time.monotonic() - t_stage, 2)
                attempt["error"] = attempt["error"] or f"pages: {type(exc).__name__}: {exc}"[:200]
            if images and attempt["pages"] == "PASS":
                t_stage = time.monotonic()
                status, n_ok, n_tried, img_err, t_find, t_bytes = check_images(
                    conn, page_list, image_samples
                )
                attempt["t_images"] = round(time.monotonic() - t_stage, 2)
                attempt["t_find_page"] = round(t_find, 2)
                attempt["images"] = status
                attempt["n_images_ok"] = n_ok
                attempt["n_images_tried"] = n_tried
                if status != "PASS" and not attempt["error"]:
                    attempt["error"] = f"images: {img_err}"[:200]
        attempt["depth"] = _depth(attempt)
        if attempt["depth"] > best["depth"]:
            best = attempt
        if attempt["depth"] >= target_depth:
            break  # fully working — no need to try more series

    result["detail"] = best["detail"]
    result["chapters"] = best["chapters"]
    result["pages"] = best["pages"]
    result["images"] = best["images"]
    result["n_chapters"] = best["n_chapters"]
    result["n_pages"] = best["n_pages"]
    result["n_images_ok"] = best["n_images_ok"]
    result["n_images_tried"] = best["n_images_tried"]
    result["series_sample"] = best["sample"]
    result["error"] = best["error"]
    for stage in ("detail", "chapters", "pages", "images"):
        result["t"][stage] = best[f"t_{stage}"]
    result["t_find_page"] = best["t_find_page"]
    required = READ_STAGES if images else READ_STAGES[:-1]
    result["ok"] = all(result[s] == "PASS" for s in required)
    result["secs"] = round(time.monotonic() - t0, 1)
    return result


#: Packages shipped by --sync-code. ``services`` is in the list because the
#: image stage runs through ``BrowseService._fetch_url`` -- a change to the
#: image proxy's transport is invisible to a connectors-only overlay, so the
#: probe would report the deployed timings and call them verified.
SYNC_PACKAGES = ("connectors", "services")


def _sync_code_to_container() -> str:
    """Ship the working tree's source packages into the container as an overlay.

    Verifying a fix means running the *new* code against the live site from
    the production egress IP. Rebuilding the image for each attempt is far too
    slow, and overwriting /app would mutate the running service. So the tree
    goes to a scratch dir that is prepended to sys.path for the probe process
    only; the served app is untouched.
    """
    overlay = "/app/_probe_overlay"
    host_dir = "/tmp/mm_probe_overlay"
    packages = " ".join(SYNC_PACKAGES)
    print(f"==> syncing working-tree {packages} -> {VPS_CONTAINER}:{overlay}", flush=True)
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", VPS_HOST,
         "mkdir -p " + " ".join(f"{host_dir}/{pkg}" for pkg in SYNC_PACKAGES)],
        check=True,
    )
    for pkg in SYNC_PACKAGES:
        subprocess.run(
            ["rsync", "-az", "--delete", "-e", "ssh -o BatchMode=yes",
             "--exclude", "__pycache__", "--exclude", "*.pyc",
             f"{REPO}/{pkg}/", f"{VPS_HOST}:{host_dir}/{pkg}/"],
            check=True,
        )
    copies = " && ".join(
        f"docker cp {host_dir}/{pkg} {VPS_CONTAINER}:{overlay}/{pkg}"
        for pkg in SYNC_PACKAGES
    )
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", VPS_HOST,
         f"docker exec {VPS_CONTAINER} rm -rf {overlay} && "
         f"docker exec {VPS_CONTAINER} mkdir -p {overlay} && "
         + copies],
        check=True,
    )
    return overlay


def _run_remote(argv: list[str], out: str, probe_out: str, sync_code: bool = False) -> int:
    """Re-run this script inside the production container over ssh.

    Probing from a laptop is actively misleading — residential egress sails
    past bot walls that reject the VPS, so a local run reports dead sources as
    live. This ships the script to the box and execs it in the backend
    container, which has the exact TLS stack, headers and egress IP prod uses,
    then copies the JSON results back so the local repo holds VPS truth.

    The script lands in /app/scripts/ so ``parents[1]`` still resolves to the
    app root the way it does in the repo.
    """
    script = Path(__file__).resolve()
    host_tmp = "/tmp/e2e_connector_check.py"
    ctr_out = "/tmp/e2e_results.json"
    ctr_probe = "/tmp/probe_results.json"

    inner_args = list(argv) + ["--out", ctr_out]
    if probe_out:
        inner_args += ["--probe-out", ctr_probe]
    inner = " ".join(shlex.quote(a) for a in inner_args)

    overlay = _sync_code_to_container() if sync_code else ""

    print(f"==> copying {script.name} to {VPS_HOST}:{host_tmp}", flush=True)
    subprocess.run(
        ["scp", "-o", "BatchMode=yes", str(script), f"{VPS_HOST}:{host_tmp}"],
        check=True,
    )
    print(f"==> exec in {VPS_CONTAINER}: {inner}"
          + (f"  [overlay {overlay}]" if overlay else ""), flush=True)
    remote_cmd = (
        f"set -e; docker exec {VPS_CONTAINER} mkdir -p /app/scripts; "
        f"docker cp {host_tmp} {VPS_CONTAINER}:/app/scripts/_e2e_check.py; "
        f"docker exec -w /app -e MM_PROBE_FROM=vps "
        + (f"-e MM_PROBE_OVERLAY={overlay} " if overlay else "")
        + f"{VPS_CONTAINER} "
        f"python /app/scripts/_e2e_check.py {inner}; "
        f"rc=$?; docker exec {VPS_CONTAINER} rm -f /app/scripts/_e2e_check.py; "
        f"docker cp {VPS_CONTAINER}:{ctr_out} {host_tmp}.out.json 2>/dev/null || true; "
        + (f"docker cp {VPS_CONTAINER}:{ctr_probe} {host_tmp}.probe.json 2>/dev/null || true; "
           if probe_out else "")
        + "exit $rc"
    )
    rc = subprocess.run(["ssh", "-o", "BatchMode=yes", VPS_HOST, remote_cmd]).returncode

    for remote_file, local_path in (
        (f"{host_tmp}.out.json", out),
        (f"{host_tmp}.probe.json", probe_out),
    ):
        if not local_path:
            continue
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        fetched = subprocess.run(
            ["scp", "-o", "BatchMode=yes", f"{VPS_HOST}:{remote_file}", local_path]
        )
        if fetched.returncode == 0:
            print(f"==> pulled {local_path}")
    return rc


def _write_probe_results(results: list[dict], path: Path, mature_ids: set[str]) -> None:
    """Emit docs/connector_probe_results.json in the established shape.

    Keeps the keys the existing consumers read (``generate_connector_status``,
    ``apply_probe_prune``: source_id/status/items/mature/detail/sample_title)
    and adds the per-stage breakdown, because "browse works" and "a chapter is
    readable" are different facts and only the second one matters to a reader.
    """
    out: list[dict] = []
    for r in results:
        timings = r.get("t") or {}
        if r["ok"]:
            status = "LIVE"
        elif r["browse"] == "PASS":
            # lists fine but the read path is broken somewhere downstream
            status = "PARTIAL"
        elif r["browse"] in ("TIMEOUT", "ERROR"):
            status = "ERROR"
        else:
            status = "DEAD"
        out.append({
            "source_id": r["source_id"],
            "status": status,
            "items": r.get("n_series", 0),
            "mature": r["source_id"] in mature_ids,
            "detail": r.get("error", "") or "",
            "sample_title": r.get("series_sample", "") or "",
            "stages": {s: r.get(s, "-") for s in STAGES},
            # Seconds per stage, measured on the VPS against the live site.
            # ``images`` covers find_page + the byte fetch for 3 sampled pages;
            # ``find_page`` is broken out because a big number there is an N+1
            # in the connector, not the CDN.
            "timings_secs": {
                **{s: round(float(timings.get(s, 0.0)), 2) for s in STAGES},
                "find_page": round(float(r.get("t_find_page", 0.0)), 2),
                "total": round(float(r.get("secs", 0.0)), 2),
            },
            "search_hits": r.get("n_search", 0),
            "n_chapters": r.get("n_chapters", 0),
            "n_pages": r.get("n_pages", 0),
            "n_images_ok": r.get("n_images_ok", 0),
            "n_images_tried": r.get("n_images_tried", 0),
        })
    out.sort(key=lambda r: ({"LIVE": 0, "PARTIAL": 1, "DEAD": 2, "ERROR": 3}[r["status"]],
                            r["source_id"]))
    counts = {k: sum(1 for r in out if r["status"] == k)
              for k in ("LIVE", "PARTIAL", "DEAD", "ERROR")}
    from datetime import UTC, datetime

    payload = {
        "probed_at": datetime.now(UTC).isoformat(),
        "probed_from": "vps" if os.environ.get("MM_PROBE_FROM") == "vps" else "unknown",
        "total": len(out),
        "live": counts["LIVE"],
        "partial": counts["PARTIAL"],
        "dead": counts["DEAD"],
        "error": counts["ERROR"],
        "results": out,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {path} "
          f"(LIVE {counts['LIVE']} / PARTIAL {counts['PARTIAL']} / "
          f"DEAD {counts['DEAD']} / ERROR {counts['ERROR']})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mature", action="store_true", help="include mature connectors")
    ap.add_argument("--only", default="", help="comma-separated source_ids to check")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--timeout", type=float, default=90.0,
                    help="per-connector budget in seconds, checked at stage boundaries")
    ap.add_argument("--deadline", type=float, default=1800.0,
                    help="hard wall-clock cap for the whole run in seconds")
    ap.add_argument("--out", default=str(REPO / "docs" / "connector_e2e_results.json"))
    ap.add_argument("--probe-out", default="",
                    help="also write docs/connector_probe_results.json-shaped JSON here")
    ap.add_argument("--no-search", dest="search", action="store_false",
                    help="skip the search stage")
    ap.add_argument("--no-images", dest="images", action="store_false",
                    help="skip the image-bytes stage (browse/detail/chapters/pages only)")
    ap.add_argument("--image-samples", type=int, default=3,
                    help="pages per chapter to fetch bytes for (first/middle/last)")
    ap.add_argument("--remote", action="store_true",
                    help="run this check inside the production container over ssh")
    ap.add_argument("--sync-code", action="store_true",
                    help="with --remote: overlay the working tree's connectors/ "
                         "so a fix is verified before it is deployed")
    args = ap.parse_args()

    if args.remote:
        # --out/--probe-out are rewritten to container paths and copied back
        passthrough: list[str] = []
        skip_next = False
        for a in sys.argv[1:]:
            if skip_next:
                skip_next = False
                continue
            if a in ("--remote", "--sync-code"):
                continue
            if a in ("--out", "--probe-out"):
                skip_next = True
                continue
            if a.startswith(("--out=", "--probe-out=")):
                continue
            passthrough.append(a)
        raise SystemExit(
            _run_remote(passthrough, args.out, args.probe_out, sync_code=args.sync_code)
        )

    descriptors = list(list_installed_connectors(include_mature=True))
    ids = [d.source_type for d in descriptors]
    if not args.mature:
        mature = {d.source_type for d in descriptors if getattr(d, "mature", False)}
        ids = [i for i in ids if i not in mature]
    if args.only:
        want = {s.strip() for s in args.only.split(",") if s.strip()}
        ids = [i for i in ids if i in want]
    # local_filesystem needs config; skip in the live web check
    ids = [i for i in ids if i != "local_filesystem"]

    print(f"Checking {len(ids)} connectors "
          f"(workers={args.workers}, timeout={args.timeout}s, mature={args.mature}, "
          f"images={args.images})...",
          flush=True)

    def _stub(sid: str, stage_status: str, error: str, secs: float) -> dict:
        return {
            "source_id": sid, "browse": stage_status, "search": "-", "detail": "-",
            "chapters": "-", "pages": "-", "images": "-", "series_sample": "",
            "search_term": "", "n_series": 0, "n_search": 0, "n_chapters": 0,
            "n_pages": 0, "n_images_ok": 0, "n_images_tried": 0,
            "error": error, "ok": False, "secs": secs,
            # A timeout is a latency measurement too: attribute the whole
            # budget to browse so the slow-source ranking still sees it.
            "t": {st: (secs if st == "browse" else 0.0) for st in STAGES},
            "t_find_page": 0.0,
        }

    results: list[dict] = []
    # NOTE: the old loop passed --timeout to fut.result() inside as_completed,
    # which can never fire (as_completed only yields already-finished futures),
    # so a wedged source could stall the whole audit. The budget is now spent
    # inside check_one, and cf.wait caps the run as a whole.
    ex = cf.ThreadPoolExecutor(max_workers=args.workers)
    futs = {
        ex.submit(check_one, sid, images=args.images,
                  image_samples=args.image_samples, search=args.search,
                  budget=args.timeout): sid
        for sid in ids
    }
    done, not_done = cf.wait(futs, timeout=args.deadline)
    for fut in done:
        sid = futs[fut]
        try:
            results.append(fut.result())
        except Exception as exc:  # noqa: BLE001
            results.append(_stub(sid, "ERROR", f"{type(exc).__name__}: {exc}"[:200], 0.0))
    for fut in not_done:
        sid = futs[fut]
        results.append(_stub(sid, "TIMEOUT", f"still running at deadline "
                                             f"{args.deadline:.0f}s", args.timeout))
    # Threads stuck in a socket read cannot be joined in bounded time; do not
    # wait on them. The results above are already complete.
    ex.shutdown(wait=False, cancel_futures=True)

    results.sort(key=lambda r: (not r["ok"], r["source_id"]))
    fully_ok = [r for r in results if r["ok"]]
    # browse works but the reader path does not — the population worth fixing
    partial = [r for r in results if not r["ok"] and r["browse"] == "PASS"]

    def mark(v: str) -> str:
        return {"PASS": "✅", "FAIL": "❌", "PARTIAL": "◐", "TIMEOUT": "⏱",
                "ERROR": "💥", "-": "·"}.get(v, v)

    print()
    print(f"{'source':22} {'br':>2} {'se':>2} {'de':>2} {'ch':>2} {'pg':>2} {'im':>2}  "
          f"{'browse':>6} {'srch':>5} {'detl':>5} {'chap':>5} {'page':>5} {'img':>5} "
          f"{'TOTAL':>6}  sample / error")
    print("-" * 150)
    for r in results:
        t = r.get("t") or {}
        tail = r["series_sample"] if r["ok"] else (r["error"] or r["series_sample"])
        print(f"{r['source_id']:22} "
              f"{mark(r['browse']):>2} {mark(r.get('search', '-')):>2} "
              f"{mark(r['detail']):>2} {mark(r['chapters']):>2} "
              f"{mark(r['pages']):>2} {mark(r['images']):>2}  "
              f"{t.get('browse', 0):>6.2f} {t.get('search', 0):>5.2f} "
              f"{t.get('detail', 0):>5.2f} {t.get('chapters', 0):>5.2f} "
              f"{t.get('pages', 0):>5.2f} {t.get('images', 0):>5.2f} "
              f"{r['secs']:>6.1f}  {tail[:40]}")

    print("-" * 150)
    label = "browse+detail+chapters+pages" + ("+images" if args.images else "")
    print(f"FULLY WORKING ({label}): {len(fully_ok)}/{len(results)}")
    print("  " + ", ".join(r["source_id"] for r in fully_ok))
    if partial:
        print(f"\nPARTIAL (browses, but read path broken): {len(partial)}")
        for r in partial:
            failed = next((s for s in READ_STAGES if r[s] not in ("PASS", "-")), "?")
            print(f"  {r['source_id']:22} fails at {failed:9} {r['error'][:60]}")

    # Speed is half the audit: rank the working sources the owner waits on.
    slow = sorted((r for r in results if r["ok"]), key=lambda r: -r["secs"])
    slow = [r for r in slow if r["secs"] >= SLOW_TOTAL_SECS]
    if slow:
        print(f"\nSLOW but working (>= {SLOW_TOTAL_SECS:.0f}s end to end): {len(slow)}")
        for r in slow:
            t = r.get("t") or {}
            worst = max(STAGES, key=lambda s: t.get(s, 0.0))
            print(f"  {r['source_id']:22} {r['secs']:>6.1f}s   worst stage: "
                  f"{worst} {t.get(worst, 0.0):.2f}s   "
                  f"find_page {r.get('t_find_page', 0.0):.2f}s")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({
        "checked": len(results),
        "fully_working": len(fully_ok),
        "results": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {args.out}")

    if args.probe_out:
        mature_ids = {d.source_type for d in descriptors if getattr(d, "mature", False)}
        _write_probe_results(results, Path(args.probe_out), mature_ids)

    if not_done:
        # ThreadPoolExecutor's atexit hook joins its worker threads, so a
        # source wedged in a socket read would hang the process forever after
        # the report is already written. Everything is flushed; leave now.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)


if __name__ == "__main__":
    main()
