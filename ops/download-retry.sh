#!/usr/bin/env bash
# Re-queue failed downloads and make sure the worker pool is actually running.
#
# Two distinct stalls this recovers from:
#
#  1. Failed chapters. A chapter that errors is left status=failed with its
#     queue row back at 'pending' -- the dispatcher requires status='queued'
#     AND state='pending', so a failed row is skipped forever. It does not
#     block anything, it just never runs again without being reset.
#
#  2. A drained pool. The manager is event-driven: _dispatch() runs on start,
#     on notify_change(), and in each worker's finally block. There is NO poll
#     loop. If every in-flight chapter finishes or fails at the same moment,
#     nothing is left to call _dispatch() and a queue with pending rows sits
#     idle indefinitely.
#
# Restarting is how (2) is fixed, and it is safe: partial files plus HTTP Range
# resume plus a SHA-256 verified page skip mean an interrupted chapter picks up
# where it left off rather than starting over, and _recover_interrupted()
# re-queues anything caught mid-flight.
set -euo pipefail

CONTAINER="${1:-manhwamaniacs-production-backend}"
LOG="${MM_RETRY_LOG:-/var/log/mm-download-retry.log}"

say() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG" 2>/dev/null || printf '%s %s\n' "$(date '+%F %T')" "$*"; }

docker inspect "$CONTAINER" >/dev/null 2>&1 || { say "no container $CONTAINER"; exit 1; }

STATE=$(docker exec -i "$CONTAINER" python - <<'PY' 2>/dev/null || true
from database.session import SessionLocal
from database.models import Download, DownloadQueue
from sqlalchemy import func

db = SessionLocal()
counts = dict(db.query(Download.status, func.count()).group_by(Download.status).all())

# Reset failures so the dispatcher can see them again. Deliberately NOT
# touching 'cancelled' -- that was a human decision, not a fault.
failed = db.query(Download).filter(Download.status.in_(("failed", "paused"))).all()
for row in failed:
    row.status = "queued"
    if row.queue is not None:
        row.queue.state = "pending"
db.commit()

print(f"RESET\t{len(failed)}")
print(f"QUEUED\t{counts.get('queued', 0)}")
print(f"ACTIVE\t{counts.get('downloading', 0)}")
print(f"DONE\t{counts.get('completed', 0)}")
PY
)

RESET=$(awk -F'\t' '/^RESET/{print $2}' <<<"$STATE")
QUEUED=$(awk -F'\t' '/^QUEUED/{print $2}' <<<"$STATE")
ACTIVE=$(awk -F'\t' '/^ACTIVE/{print $2}' <<<"$STATE")
DONE=$(awk -F'\t' '/^DONE/{print $2}' <<<"$STATE")

say "reset=${RESET:-0} queued=${QUEUED:-0} active=${ACTIVE:-0} done=${DONE:-0}"

# Nothing left to do: do not restart a healthy idle server for no reason.
if [ "${QUEUED:-0}" -eq 0 ] && [ "${RESET:-0}" -eq 0 ]; then
  say "queue empty — nothing to run"
  exit 0
fi

# Work is waiting but no worker is moving: the pool has drained and only a
# start() will call _dispatch() again.
if [ "${ACTIVE:-0}" -eq 0 ]; then
  say "work pending but pool idle — restarting to re-dispatch"
  docker restart "$CONTAINER" >/dev/null
  until docker exec "$CONTAINER" python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4)" >/dev/null 2>&1; do
    sleep 3
  done
  say "back up"
else
  say "pool already busy — left alone"
fi
