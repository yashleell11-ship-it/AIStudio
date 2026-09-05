#!/usr/bin/env bash
# ManhwaManiacs — OVH VPS deploy. Run on the VPS from the repo checkout
# (default /srv/manhwamaniacs/app). Idempotent.
#
#   ops/vps/deploy.sh                  build + (re)start the stack, run migrations
#   ops/vps/deploy.sh create-owner     one-off: create the admin/owner account
#                                      (non-TTY: set MM_OWNER_USER/MM_OWNER_PASS,
#                                      or use `ssh -t`)
#   ops/vps/deploy.sh reset-accounts   DESTRUCTIVE: delete every account + its
#                                      data, re-arm the bootstrap window
#                                      (confirm by typing RESET, or MM_CONFIRM=RESET)
#   ops/vps/deploy.sh set-invite-code [CODE|clear]
#                                      set/rotate (or clear) the registration
#                                      invite code; generates one if omitted
#   ops/vps/deploy.sh logs             tail both containers
#   ops/vps/deploy.sh edge             (re)install the Caddy + cloudflared routing
#
# Prereqs (one-time, done by `edge` + the OVH panel):
#   - /srv/manhwamaniacs on the 50 GB disk, owned by uid 1000
#   - the Minecraft stack's Caddy + cloudflared running (mcbots compose)
#   - DNS: manhwamaniacs.xyz / www / app  CNAME -> <mcbots tunnel>.cfargotunnel.com

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE=(docker compose -f "$REPO/ops/vps/docker-compose.yml")
DATA_ROOT=/srv/manhwamaniacs
EDGE_DIR=/opt/mcbots/edge
CF_ID=e40ede74-c9c0-454d-9983-3a6ce2866a47

ensure_dirs() {
  for d in data apk ipa; do mkdir -p "$DATA_ROOT/$d"; done
  # backend runs as uid 1000; it must own the data dir
  sudo chown -R 1000:1000 "$DATA_ROOT/data" || true
}

cmd_deploy() {
  ensure_dirs
  cd "$REPO"
  export GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo dev)"
  export GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  echo ">> building $GIT_BRANCH @ $GIT_COMMIT"
  "${COMPOSE[@]}" build
  "${COMPOSE[@]}" up -d
  echo ">> waiting for health"
  for i in $(seq 1 30); do
    if docker inspect --format '{{.State.Health.Status}}' manhwamaniacs-frontend 2>/dev/null | grep -q healthy \
    && docker inspect --format '{{.State.Health.Status}}' manhwamaniacs-backend  2>/dev/null | grep -q healthy; then
      echo ">> both healthy"; break
    fi
    sleep 3
  done
  "${COMPOSE[@]}" ps
  echo ">> in-container health:"
  docker exec manhwamaniacs-backend python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).read().decode())" || true

  # Prove the CODE deployed, not just the version label.
  #
  # /app/version reads mobile/pubspec.yaml, which is a bind mount — so it
  # reports the new version the moment the file rsyncs, before this rebuild
  # runs, and would keep reporting it even if the rebuild had failed. The
  # changelog is compiled into the image, so the two agreeing is the cheapest
  # honest evidence that the container is running the source we just shipped.
  # It also catches a version bumped without its release-notes entry.
  echo ">> deployed-code check:"
  if ! docker exec manhwamaniacs-backend python - <<'PYCHECK'
import json, sys, time, urllib.request

def get(path):
    with urllib.request.urlopen(f"http://127.0.0.1:8000{path}", timeout=6) as r:
        return json.loads(r.read().decode())

for attempt in range(5):
    try:
        pubspec = get("/app/version")["version"]
        compiled = get("/app/changelog")["entries"][0]["version"]
        break
    except Exception as exc:  # noqa: BLE001 - any transport failure is a retry
        if attempt == 4:
            print(f"!! could not reach the app to verify it: {exc}")
            sys.exit(1)
        time.sleep(3)

if pubspec == compiled:
    print(f">> serving {pubspec} — mounted pubspec and compiled changelog agree")
    sys.exit(0)

print(f"!! MISMATCH: /app/version says {pubspec}, compiled changelog says {compiled}")
print("!! the container is serving code older than the mounted pubspec, or the")
print("!! release-notes entry for this version was never added")
sys.exit(1)
PYCHECK
  then
    echo ">> DEPLOY NOT VERIFIED — see the mismatch above" >&2
    return 1
  fi

  # cmd_install_timers documents itself as idempotent and safe to re-run after
  # every deploy, but nothing ever called it — so the iOS pull loop was closed
  # only by someone remembering an undocumented subcommand, which is exactly how
  # two green builds once sat unpublished. A subshell contains its `exit 1`, and
  # a failure here must not fail an otherwise healthy deploy.
  ( cmd_install_timers ) || echo ">> WARNING: could not install the iOS fetch timer"
}

cmd_create_owner() {
  # Runs inside the backend container so it uses the same DB + code.
  #
  # Credentials come from MM_OWNER_USER / MM_OWNER_PASS when set; otherwise we
  # prompt — but ONLY on a real terminal. Under `ssh host 'deploy.sh
  # create-owner'` there is no TTY, `read -rp` prints nothing and blocks
  # forever waiting on a closed stdin (the owner hit exactly this hang), so a
  # non-TTY run without env vars is refused with instructions instead.
  local U="${MM_OWNER_USER:-}" P="${MM_OWNER_PASS:-}"
  if [ -z "$U" ] || [ -z "$P" ]; then
    if [ -t 0 ]; then
      read -rp "Owner username [yeahiamyash]: " U; U="${U:-yeahiamyash}"
      read -rsp "Owner password: " P; echo
    else
      echo "!! create-owner needs a terminal to prompt, and stdin is not a TTY." >&2
      echo "   Either allocate one:   ssh -t <host> '$0 create-owner'" >&2
      echo "   or pass credentials:   MM_OWNER_USER=... MM_OWNER_PASS=... $0 create-owner" >&2
      exit 2
    fi
  fi
  if [ -z "$P" ]; then echo "!! empty password refused" >&2; exit 2; fi
  docker exec -e MM_OWNER_USER="$U" -e MM_OWNER_PASS="$P" -i manhwamaniacs-backend python - <<'PY'
import os
from database.session import SessionLocal, init_db
from services.auth_service import AuthService
init_db()
db = SessionLocal()
try:
    svc = AuthService(db)
    user = svc.register(username=os.environ["MM_OWNER_USER"], password=os.environ["MM_OWNER_PASS"])
    db.commit()
    print(f"created user id={user.id} is_admin={bool(user.is_admin)}")
finally:
    db.close()
PY
}

# Tables deleted by reset-accounts, children first so the raw DELETEs never
# trip a foreign key regardless of each FK's ON DELETE clause. Everything here
# is account-owned; global state (source cache, OCR text, update settings/runs)
# is deliberately NOT touched.
RESET_TABLES="update_notifications profile_series_tags tags collection_series collections reading_sessions bookmarks chapter_progress followed_series source_pins reading_profiles sessions users"

cmd_reset_accounts() {
  echo ">> counting what a reset would destroy..."
  docker exec -e RESET_TABLES="$RESET_TABLES" -i manhwamaniacs-backend python - <<'PY'
import os
from sqlalchemy import text
from database.session import get_engine
with get_engine().connect() as conn:
    total = 0
    for t in os.environ["RESET_TABLES"].split():
        n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one()
        total += n
        print(f"   {t:24s} {n:8d} row(s)")
    print(f"   {'TOTAL':24s} {total:8d} row(s)")
PY

  cat <<'WARN'

  ############################################################################
  ##  DESTRUCTIVE: this permanently deletes EVERY account and everything    ##
  ##  owned by them — users, sessions, reading profiles, follows, reading   ##
  ##  progress, reading history, bookmarks, collections, and tags — the     ##
  ##  row counts above are the real blast radius. There is no undo.         ##
  ##                                                                        ##
  ##  It then re-arms the bootstrap window: for the next                    ##
  ##  MM_BOOTSTRAP_WINDOW_MINUTES (default 30) the FIRST account to         ##
  ##  register on the PUBLIC site becomes admin. Plan to claim it           ##
  ##  immediately (or use create-owner, which needs no window).             ##
  ############################################################################

WARN

  if [ "${MM_CONFIRM:-}" = "RESET" ]; then
    echo ">> confirmed via MM_CONFIRM=RESET"
  elif [ -t 0 ]; then
    read -rp "Type RESET (all caps) to proceed, anything else aborts: " CONFIRM
    if [ "$CONFIRM" != "RESET" ]; then echo ">> aborted, nothing deleted"; exit 1; fi
  else
    echo "!! refusing: no TTY to confirm on. Re-run with MM_CONFIRM=RESET $0 reset-accounts" >&2
    echo "   (or over ssh -t for an interactive prompt)" >&2
    exit 2
  fi

  docker exec -e RESET_TABLES="$RESET_TABLES" -i manhwamaniacs-backend python - <<'PY'
import os
from sqlalchemy import text
from core.time_utils import utcnow
from database.session import get_engine
with get_engine().begin() as conn:
    for t in os.environ["RESET_TABLES"].split():
        n = conn.execute(text(f"DELETE FROM {t}")).rowcount
        print(f"   deleted {n:8d} row(s) from {t}")
    # Re-arm the bootstrap window explicitly (fresh timestamp, same
    # transaction as the wipe): the next MM_BOOTSTRAP_WINDOW_MINUTES admit one
    # uninvited registration that becomes admin.
    conn.execute(text("DELETE FROM bootstrap_state"))
    conn.execute(
        text("INSERT INTO bootstrap_state (id, empty_since) VALUES (1, :now)"),
        {"now": utcnow()},
    )
    print("   bootstrap window re-armed (empty_since = now)")
PY

  local WINDOW="${MM_BOOTSTRAP_WINDOW_MINUTES:-30}"
  cat <<EOF

  Done. All accounts are gone and the bootstrap window is OPEN.

  !! CLAIM IT FROM THIS SHELL, NOT THROUGH THE PUBLIC SITE:
         $0 create-owner

  An adversarial audit demonstrated a live race in the public path: the
  emptiness check and the INSERT are not serialized, so N simultaneous
  POST /auth/register calls on an empty table ALL pass the check and ALL
  become admin — bypassing MM_REGISTRATION_ENABLED=false. Six concurrent
  requests produced five admins on the real app. GET /auth/bootstrap-status
  is unauthenticated and unthrottled, so it is a free oracle telling an
  attacker the exact moment this window opens.

  create-owner runs inside the container against the same DB and does not
  race, because nothing else is registering. Until the backend fix lands
  (serialize the claim + a single-admin DB constraint), treat public
  bootstrap registration as unsafe on this host.
  If the window lapses before anyone registers, uninvited signup locks again;
  either run create-owner (always works) or re-run reset-accounts to re-arm.
  Afterwards, let household members in via an invite code:
         $0 set-invite-code            # then flip MM_REGISTRATION_ENABLED=true
EOF
}

cmd_set_invite_code() {
  local CODE="${1:-${MM_INVITE_CODE:-}}"
  if [ "$CODE" = "clear" ]; then
    echo ">> clearing the invite code (registration falls back to MM_REGISTRATION_ENABLED alone)"
    CODE=""
  elif [ -z "$CODE" ]; then
    CODE="$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 16)"
    echo ">> no code given — generated one"
  elif [ "${#CODE}" -lt 8 ]; then
    echo "!! refusing an invite code shorter than 8 characters — short codes are" >&2
    echo "   brute-forceable even behind the register rate limit. Omit the" >&2
    echo "   argument to have a strong one generated." >&2
    exit 2
  fi

  # Persist into /data/settings.json (survives restarts; the /data volume is
  # the DB's home). The running server caches Settings for the process
  # lifetime, so restart the container to pick it up.
  docker exec -e NEW_CODE="$CODE" -i manhwamaniacs-backend python - <<'PY'
import os
from core.config import update_persisted_settings
code = os.environ.get("NEW_CODE") or None
update_persisted_settings(registration_invite_code=code)
print(f"   persisted registration_invite_code ({'set, %d chars' % len(code) if code else 'cleared'}) in settings.json")
PY
  echo ">> restarting backend so the running process re-reads settings"
  docker restart manhwamaniacs-backend >/dev/null
  echo ">> backend restarted"

  if docker exec manhwamaniacs-backend printenv MM_REGISTRATION_INVITE_CODE >/dev/null 2>&1; then
    echo "!! WARNING: the container has MM_REGISTRATION_INVITE_CODE set in its"
    echo "   environment (ops/vps/docker-compose.yml). Env OVERRIDES the value"
    echo "   just persisted — update/remove that compose line and 'docker"
    echo "   compose up -d backend' or this change has no effect."
  fi

  cat <<EOF

  Invite code: ${CODE:-<cleared>}

  Notes:
    - The code only matters while registration is enabled. The committed
      compose default is MM_REGISTRATION_ENABLED=false (fully closed). To let
      household members sign up, set MM_REGISTRATION_ENABLED=true in
      ops/vps/docker-compose.yml AND keep an invite code set — enabling
      registration with no code is OPEN registration on a public host.
    - settings.json (on the /data volume) now carries the code across
      restarts. To manage it via compose instead, set
      MM_REGISTRATION_INVITE_CODE=<code> in ops/vps/docker-compose.yml
      (env wins over settings.json).
    - Share the code out-of-band; the API never echoes it.
EOF
}

cmd_logs() { "${COMPOSE[@]}" logs -f --tail 100; }

cmd_edge() {
  # Idempotently add the manhwamaniacs vhosts + tunnel ingress to the
  # Minecraft stack's edge, then reload.
  local CADDY="$EDGE_DIR/Caddyfile"
  local CFG="$EDGE_DIR/cloudflared/config.yml"

  if ! grep -q "manhwamaniacs.xyz" "$CADDY"; then
    echo ">> appending manhwamaniacs vhosts to $CADDY"
    sudo tee -a "$CADDY" >/dev/null <<'CADDYEOF'

# ======================= ManhwaManiacs (co-tenant) =======================
www.manhwamaniacs.xyz:80 {
	import sec
	redir https://manhwamaniacs.xyz{uri} 308
}

manhwamaniacs.xyz:80 {
	import sec
	import zip
	import logroll manhwamaniacs
	# cloudflared forwards the ORIGINAL edge scheme in X-Forwarded-Proto, so a
	# plain-http hit at the Cloudflare edge is detectable here even though the
	# tunnel hop is always http. Without this the apex served the real login
	# page over cleartext (the www host always redirected; the apex did not).
	@insecure header X-Forwarded-Proto http
	redir @insecure https://manhwamaniacs.xyz{uri} 308
	header Strict-Transport-Security "max-age=300"
	reverse_proxy manhwamaniacs-frontend:3000
}

# APK / IPA install landing + SideStore source — served by the backend directly.
app.manhwamaniacs.xyz:80 {
	import sec
	import zip
	import logroll manhwamaniacs-app
	@insecure header X-Forwarded-Proto http
	redir @insecure https://app.manhwamaniacs.xyz{uri} 308
	header Strict-Transport-Security "max-age=300"
	reverse_proxy manhwamaniacs-backend:8000
}
CADDYEOF
  else
    echo ">> Caddyfile already has manhwamaniacs.xyz — skipping"
  fi

  if ! grep -q "manhwamaniacs.xyz" "$CFG"; then
    echo ">> adding tunnel ingress rules to $CFG"
    # Insert the three hostnames before the catch-all 404 line.
    sudo python3 - "$CFG" <<'PYEOF'
import sys, io
p = sys.argv[1]
lines = io.open(p).read().splitlines()
out, inserted = [], False
add = [
    "  - hostname: manhwamaniacs.xyz",
    "    service: http://caddy:80",
    "  - hostname: www.manhwamaniacs.xyz",
    "    service: http://caddy:80",
    "  - hostname: app.manhwamaniacs.xyz",
    "    service: http://caddy:80",
]
for ln in lines:
    if not inserted and ln.strip().startswith("- service: http_status:404"):
        out.extend(add); inserted = True
    out.append(ln)
io.open(p, "w").write("\n".join(out) + "\n")
print("done" if inserted else "WARN: catch-all line not found; appended nothing")
PYEOF
  else
    echo ">> cloudflared config already has manhwamaniacs.xyz — skipping"
  fi

  echo ">> reloading Caddy"
  docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
  echo ">> restarting cloudflared"
  docker restart cloudflared
  echo ">> edge updated. Remaining manual step: DNS (see below)"
  cat <<EOF

  Cloudflare dashboard -> manhwamaniacs.xyz -> DNS -> Records:
    CNAME  @      ${CF_ID}.cfargotunnel.com   Proxied
    CNAME  www    ${CF_ID}.cfargotunnel.com   Proxied
    CNAME  app    ${CF_ID}.cfargotunnel.com   Proxied
  (delete or repoint any old 'staging' record; the old NAS tunnel target is dead)
EOF
}

# -----------------------------------------------------------------------------
# install-timers: automate the iOS build pickup.
#
# iOS builds happen on GitHub's cloud Mac; this box has to pull the result before
# a phone can see it. That pull was manual, which meant a green CI build could sit
# unpublished indefinitely while SideStore kept advertising an older version — the
# update badge simply never appeared. A timer closes that loop.
#
# Idempotent: safe to re-run after every deploy.
# -----------------------------------------------------------------------------
cmd_install_timers(){
  local script="$REPO/ops/fetch-ios-build.sh"
  [ -x "$script" ] || { echo "!! $script missing or not executable" >&2; exit 1; }

  echo ">> writing systemd units"
  sudo tee /etc/systemd/system/mm-fetch-ios.service >/dev/null <<EOF
[Unit]
Description=Publish the newest CI-built ManhwaManiacs iOS .ipa for SideStore
Documentation=file://$REPO/ops/fetch-ios-build.sh
# Nothing to fetch without egress; the script exits 2 ("nothing new") on failure
# to reach GitHub, which systemd would otherwise log as a hard failure.
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=ubuntu
Group=ubuntu
ExecStart=$script $DATA_ROOT/ipa
# 2 = "nothing new to publish", the ordinary outcome on most runs.
SuccessExitStatus=0 2
TimeoutStartSec=600
EOF

  sudo tee /etc/systemd/system/mm-fetch-ios.timer >/dev/null <<'EOF'
[Unit]
Description=Check for a new ManhwaManiacs iOS build every 15 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min
# Catch up after a reboot rather than waiting a full interval.
Persistent=true
# Keeps a fleet of timers from stampeding GitHub on the same second.
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable --now mm-fetch-ios.timer
  echo ">> timer active:"
  systemctl list-timers mm-fetch-ios.timer --no-pager | head -3
}

case "${1:-deploy}" in
  deploy)          cmd_deploy ;;
  create-owner)    cmd_create_owner ;;
  reset-accounts)  cmd_reset_accounts ;;
  set-invite-code) cmd_set_invite_code "${2:-}" ;;
  logs)            cmd_logs ;;
  edge)            cmd_edge ;;
  install-timers)  cmd_install_timers ;;
  *) echo "usage: $0 {deploy|create-owner|reset-accounts|set-invite-code [CODE|clear]|logs|edge|install-timers}"; exit 2 ;;
esac
