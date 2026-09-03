#!/usr/bin/env bash
# =============================================================================
# Push this working tree to the VPS and redeploy. Run from the LAPTOP.
#
# The VPS checkout has no .git (the repo is rsynced, not cloned — pushing to
# GitHub from this laptop has no credentials yet), so "deploy" means: sync the
# source, then rebuild the images there. The commit id is carried across in
# .deploy-info so the running containers can still be traced to a revision.
#
#   ops/vps/push.sh              sync frontend+backend+ops, rebuild, restart
#   ops/vps/push.sh frontend     sync only the frontend, rebuild, restart
#   ops/vps/push.sh backend      sync only the backend, rebuild, restart
#   ops/vps/push.sh apk          copy the built release APK to the app subdomain
#
# Gates: a full or frontend push runs the frontend build locally first, because
# a Next build failure on the VPS leaves the old container up but wastes a slow
# remote rebuild — and the box has 2 vCores.
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${MM_VPS_HOST:-ubuntu@135.148.43.147}"
REMOTE="${MM_VPS_PATH:-/srv/manhwamaniacs/app}"
NODE_BIN="${MM_NODE_BIN:-/home/yash/.local/node/bin}"

RSYNC_EXCLUDES=(
  --exclude .git
  --exclude node_modules
  --exclude .next
  --exclude .venv
  --exclude __pycache__
  --exclude '*.pyc'
  --exclude .pytest_cache
  --exclude manhwamaniacs.db
  --exclude build
  --exclude .dart_tool
)

say(){ printf '\033[32m==>\033[0m %s\n' "$*"; }

verify_frontend(){
  say "building the frontend locally (fail fast before a slow remote rebuild)"
  ( cd "$REPO/frontend" && PATH="$NODE_BIN:$PATH" npm run build >/dev/null )
  say "local build OK"
}

sync_dir(){
  local dir="$1"
  say "syncing $dir/"
  rsync -az --delete -e "ssh -o BatchMode=yes" "${RSYNC_EXCLUDES[@]}" \
    "$REPO/$dir/" "$HOST:$REMOTE/$dir/"
}

stamp(){
  local commit branch
  commit="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo dev)"
  branch="$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  printf '%s  %s  %s\n' "$commit" "$(date -u +%FT%TZ)" "$branch" \
    | ssh -o BatchMode=yes "$HOST" "cat > $REMOTE/.deploy-info"
  echo "$commit $branch"
}

remote_deploy(){
  local commit="$1" branch="$2"
  say "rebuilding on the VPS ($branch @ $commit)"
  ssh -o BatchMode=yes "$HOST" \
    "cd $REMOTE && GIT_COMMIT=$commit GIT_BRANCH=$branch bash ops/vps/deploy.sh deploy"
}

case "${1:-all}" in
  all)
    verify_frontend
    sync_dir frontend; sync_dir backend; sync_dir ops; sync_dir mobile
    read -r c b < <(stamp); remote_deploy "$c" "$b" ;;
  frontend)
    verify_frontend
    sync_dir frontend; sync_dir ops
    read -r c b < <(stamp); remote_deploy "$c" "$b" ;;
  backend)
    sync_dir backend; sync_dir ops
    read -r c b < <(stamp); remote_deploy "$c" "$b" ;;
  apk)
    APK="$REPO/mobile/build/app/outputs/flutter-apk/app-release.apk"
    [ -f "$APK" ] || { echo "no APK at $APK — run the release build first" >&2; exit 1; }
    say "publishing $(du -h "$APK" | cut -f1) APK"
    # The version endpoint reads the pubspec through a single-FILE bind mount,
    # and no other push mode syncs mobile/ — so without this the box happily
    # serves a 1.9.0 APK while /app/version still advertises the previous
    # release. --inplace is load-bearing: replacing a bind-mounted file
    # normally leaves the container holding the old inode, which would need a
    # container recreate to clear.
    say "syncing the pubspec the version endpoint reads"
    rsync -a --inplace -e "ssh -o BatchMode=yes" \
      "$REPO/mobile/pubspec.yaml" "$HOST:$REMOTE/mobile/pubspec.yaml"
    # Same-filesystem temp + mv so the backend never serves a half-written file.
    scp -o BatchMode=yes "$APK" "$HOST:/srv/manhwamaniacs/apk/.app-release.apk.tmp"
    ssh -o BatchMode=yes "$HOST" \
      'mv -f /srv/manhwamaniacs/apk/.app-release.apk.tmp /srv/manhwamaniacs/apk/app-release.apk \
       && sudo chown 1000:1000 /srv/manhwamaniacs/apk/app-release.apk \
       && ls -lh /srv/manhwamaniacs/apk/app-release.apk'
    say "https://app.manhwamaniacs.xyz now serves it" ;;
  *)
    echo "usage: $0 {all|frontend|backend|apk}" >&2; exit 2 ;;
esac
