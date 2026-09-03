#!/usr/bin/env bash
# ManhwaManiacs — OVH VPS deploy. Run on the VPS from the repo checkout
# (default /srv/manhwamaniacs/app). Idempotent.
#
#   ops/vps/deploy.sh                 build + (re)start the stack, run migrations
#   ops/vps/deploy.sh create-owner   one-off: create the admin/owner account
#   ops/vps/deploy.sh logs            tail both containers
#   ops/vps/deploy.sh edge            (re)install the Caddy + cloudflared routing
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
}

cmd_create_owner() {
  # Runs inside the backend container so it uses the same DB + code.
  read -rp "Owner username [yeahiamyash]: " U; U="${U:-yeahiamyash}"
  read -rsp "Owner password: " P; echo
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
    print(f"created user id={user.id} is_admin={user.is_admin}")
finally:
    db.close()
PY
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
	reverse_proxy manhwamaniacs-frontend:3000
}

# APK / IPA install landing + SideStore source — served by the backend directly.
app.manhwamaniacs.xyz:80 {
	import sec
	import zip
	import logroll manhwamaniacs-app
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

case "${1:-deploy}" in
  deploy)        cmd_deploy ;;
  create-owner)  cmd_create_owner ;;
  logs)          cmd_logs ;;
  edge)          cmd_edge ;;
  *) echo "usage: $0 {deploy|create-owner|logs|edge}"; exit 2 ;;
esac
