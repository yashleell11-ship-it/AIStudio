#!/usr/bin/env bash
# Live download progress: speed, percent, ETA, and a per-source breakdown.
#
# Reads SQLite directly rather than polling GET /downloads. That endpoint has no
# pagination and the web UI already polls it every 5s; during a bulk run it
# would serialize every queued row on every poll. GET /downloads/metrics is
# lighter but recomputes storage with a full rglob() stat walk of the whole
# downloads tree, which is O(all files) per call. Neither scales to a run this
# size, and both need a session cookie. The DB is indexed on exactly the
# columns this needs.
#
# Usage: ops/download-monitor.sh [container] [interval_seconds]
set -euo pipefail

CONTAINER="${1:-manhwamaniacs-production-backend}"
INTERVAL="${2:-3}"

command -v docker >/dev/null || { echo "docker not found" >&2; exit 1; }
docker inspect "$CONTAINER" >/dev/null 2>&1 || {
  echo "no such container: $CONTAINER" >&2; exit 1;
}

# Bytes are sampled between ticks to get real throughput; the DB stores a
# running total per row, not a rate.
PREV_BYTES=""
PREV_TS=""

cleanup() { printf '\n'; tput cnorm 2>/dev/null || true; }
trap cleanup EXIT INT TERM
tput civis 2>/dev/null || true

human() { # bytes -> human readable
  awk -v b="$1" 'BEGIN{
    split("B KB MB GB TB",u," "); i=1
    while (b>=1024 && i<5){ b/=1024; i++ }
    printf (i==1 ? "%d %s" : "%.1f %s"), b, u[i]
  }'
}

secs() { # seconds -> compact duration
  awk -v s="$1" 'BEGIN{
    if (s<=0 || s=="inf"){ print "--"; exit }
    d=int(s/86400); s-=d*86400; h=int(s/3600); s-=h*3600; m=int(s/60); s=int(s-m*60)
    if (d>0) printf "%dd %dh", d, h
    else if (h>0) printf "%dh %dm", h, m
    else if (m>0) printf "%dm %ds", m, s
    else printf "%ds", s
  }'
}

while true; do
  # One round-trip per tick. Tab-separated so a series title with spaces
  # cannot shift the fields.
  SNAPSHOT=$(docker exec -i "$CONTAINER" python - <<'PY' 2>/dev/null || true
from database.session import SessionLocal
from database.models import Download
from sqlalchemy import case, func

db = SessionLocal()
counts = dict(db.query(Download.status, func.count()).group_by(Download.status).all())
done = counts.get("completed", 0)
active = counts.get("downloading", 0)
queued = counts.get("queued", 0)
failed = counts.get("failed", 0)
paused = counts.get("paused", 0)
total = done + active + queued + failed + paused

got = db.query(func.coalesce(func.sum(Download.bytes_downloaded), 0)).scalar() or 0
print(f"TOTALS\t{done}\t{active}\t{queued}\t{failed}\t{paused}\t{total}\t{got}")

# Per-source, so it is visible that sources are running in parallel rather
# than one host taking every worker.
rows = (
    db.query(
        Download.source,
        func.sum(case((Download.status == "completed", 1), else_=0)),
        func.sum(case((Download.status == "downloading", 1), else_=0)),
        func.sum(case((Download.status == "queued", 1), else_=0)),
        func.sum(case((Download.status == "failed", 1), else_=0)),
    )
    .group_by(Download.source)
    .all()
)
for src, c, a, q, f in sorted(rows, key=lambda r: -(r[1] or 0)):
    print(f"SRC\t{src}\t{c or 0}\t{a or 0}\t{q or 0}\t{f or 0}")
PY
)

  [ -z "$SNAPSHOT" ] && { echo "cannot reach $CONTAINER"; sleep "$INTERVAL"; continue; }

  IFS=$'\t' read -r _ DONE ACTIVE QUEUED FAILED PAUSED TOTAL BYTES \
    <<<"$(grep -m1 '^TOTALS' <<<"$SNAPSHOT")"

  NOW=$(date +%s)
  RATE=0
  if [ -n "$PREV_BYTES" ] && [ "$NOW" -gt "${PREV_TS:-$NOW}" ]; then
    RATE=$(( (BYTES - PREV_BYTES) / (NOW - PREV_TS) ))
    [ "$RATE" -lt 0 ] && RATE=0
  fi
  PREV_BYTES="$BYTES"; PREV_TS="$NOW"

  REMAINING=$(( TOTAL - DONE ))
  PCT=0
  [ "$TOTAL" -gt 0 ] && PCT=$(( DONE * 100 / TOTAL ))

  # ETA from observed throughput and the mean chapter size measured on this
  # server (11.65 MB), not a guess.
  ETA="--"
  if [ "$RATE" -gt 0 ] && [ "$REMAINING" -gt 0 ]; then
    ETA=$(secs $(( REMAINING * 11650000 / RATE )))
  fi

  FILLED=$(( PCT * 40 / 100 ))
  BAR=$(printf '%*s' "$FILLED" '' | tr ' ' '#')$(printf '%*s' $(( 40 - FILLED )) '' | tr ' ' '.')

  clear
  printf '  ManhwaManiacs downloads          %s\n' "$(date '+%H:%M:%S')"
  printf '  ────────────────────────────────────────────────────\n'
  printf '  [%s] %3d%%\n\n' "$BAR" "$PCT"
  printf '  %-9s %s/s\n' "speed" "$(human "$RATE")"
  printf '  %-9s %s of %s chapters\n' "done" "$DONE" "$TOTAL"
  printf '  %-9s %s\n' "written" "$(human "$BYTES")"
  printf '  %-9s %s\n\n' "eta" "$ETA"
  printf '  %-6s %-6s %-6s %s\n' "$ACTIVE" "$QUEUED" "$FAILED" "$PAUSED"
  printf '  %-6s %-6s %-6s %s\n\n' "active" "queued" "failed" "paused"

  if grep -q '^SRC' <<<"$SNAPSHOT"; then
    printf '  %-18s %6s %6s %6s %6s\n' "source" "done" "now" "queue" "fail"
    printf '  ────────────────────────────────────────────────────\n'
    grep '^SRC' <<<"$SNAPSHOT" | head -12 | while IFS=$'\t' read -r _ s c a q f; do
      printf '  %-18s %6s %6s %6s %6s\n' "${s:0:18}" "$c" "$a" "$q" "$f"
    done
  fi

  printf '\n  ctrl-c to exit — downloads keep running\n'
  sleep "$INTERVAL"
done
