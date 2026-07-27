#!/usr/bin/env bash
# =============================================================================
# Publish the latest CI-built iOS .ipa so SideStore can install it over the air.
#
# iOS builds can't be produced here — they need macOS — so they come from the
# GitHub Actions mirror (.github/workflows/ios-build.yml) which runs on a free
# cloud Mac. This script downloads the newest successful build's artifact and
# drops it where the backend serves it from (see backend/routes/app_distribution.py,
# MM_IPA_PATH). Together with /app/source.json that turns an iOS update into a
# single tap on the phone instead of a manual download-and-sideload.
#
# Usage:
#   ops/fetch-ios-build.sh [dest-dir]        # default: /srv/apps/manhwamaniacs/production/ipa
#
# Auth: needs a GitHub token with Actions:read on the AIStudio repo, from
# $GH_TOKEN, $GITHUB_TOKEN, or ~/.gh_token. The repo is private, so artifact
# downloads are authenticated — there is no anonymous fallback.
#
# Exit codes: 0 published (or already current), 1 error, 2 nothing new to do.
# =============================================================================
set -uo pipefail

REPO="${MM_IOS_REPO:-yashleell11-ship-it/AIStudio}"
WORKFLOW="${MM_IOS_WORKFLOW:-ios-build.yml}"
BRANCH="${MM_IOS_BRANCH:-feat/profile-isolation-eclipse-warm}"
ARTIFACT="${MM_IOS_ARTIFACT:-ManhwaManiacs-ipa}"
DEST="${1:-/srv/apps/manhwamaniacs/production/ipa}"

c_grn=$'\033[32m'; c_red=$'\033[31m'; c_ylw=$'\033[33m'; c_rst=$'\033[0m'
say(){ echo "${c_grn}==>${c_rst} $*"; }
warn(){ echo "${c_ylw}!! $*${c_rst}"; }
err(){ echo "${c_red}!! $*${c_rst}" >&2; }

# ── token ────────────────────────────────────────────────────────────────────
TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
if [ -z "$TOKEN" ] && [ -r "$HOME/.gh_token" ]; then
  TOKEN="$(tr -d '[:space:]' < "$HOME/.gh_token")"
fi
if [ -z "$TOKEN" ]; then
  err "no GitHub token (set GH_TOKEN or write one to ~/.gh_token)"
  err "needs Actions:read + Contents:read on $REPO"
  exit 1
fi

api(){ curl -sS -m 60 -H "Authorization: Bearer $TOKEN" \
                      -H "Accept: application/vnd.github+json" \
                      -H "X-GitHub-Api-Version: 2022-11-28" "$@"; }

# ── newest successful run of the iOS workflow ────────────────────────────────
say "querying latest successful $WORKFLOW run on $BRANCH"
runs_json="$(api "https://api.github.com/repos/$REPO/actions/workflows/$WORKFLOW/runs?status=success&branch=$BRANCH&per_page=1")" || {
  err "GitHub API request failed"; exit 1; }

read -r RUN_ID RUN_SHA < <(python3 -c '
import json,sys
d=json.load(sys.stdin)
runs=d.get("workflow_runs") or []
if not runs:
    sys.exit(3)
print(runs[0]["id"], runs[0]["head_sha"][:7])
' <<< "$runs_json") || { err "no successful run found (or bad token / bad branch)"; exit 1; }

say "run $RUN_ID (commit $RUN_SHA)"

# Skip the download entirely when this run is already the one we published.
STAMP="$DEST/.published-run"
if [ -f "$STAMP" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$RUN_ID" ]; then
  say "run $RUN_ID already published — nothing to do"
  exit 2
fi

# ── locate the .ipa artifact for that run ────────────────────────────────────
arts_json="$(api "https://api.github.com/repos/$REPO/actions/runs/$RUN_ID/artifacts")" || {
  err "could not list artifacts"; exit 1; }

DL_URL="$(python3 -c '
import json,sys
want=sys.argv[1]
d=json.load(sys.stdin)
for a in d.get("artifacts") or []:
    if a["name"]==want and not a.get("expired"):
        print(a["archive_download_url"]); break
' "$ARTIFACT" <<< "$arts_json")"

if [ -z "$DL_URL" ]; then
  err "artifact '$ARTIFACT' not found on run $RUN_ID (expired after 90 days?)"
  exit 1
fi

# ── download + unpack ────────────────────────────────────────────────────────
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say "downloading artifact"
if ! curl -sSL -m 600 -H "Authorization: Bearer $TOKEN" -o "$TMP/artifact.zip" "$DL_URL"; then
  err "artifact download failed"; exit 1
fi

# GitHub always wraps artifacts in its own zip; the .ipa is inside.
if ! unzip -qo "$TMP/artifact.zip" -d "$TMP/unpacked"; then
  err "artifact zip is corrupt"; exit 1
fi

IPA="$(find "$TMP/unpacked" -name '*.ipa' -type f | head -1)"
if [ -z "$IPA" ]; then
  err "no .ipa inside the artifact"; exit 1
fi

# An .ipa is a zip — a truncated download would otherwise be served to phones as
# a valid-looking file that fails to install with no useful error.
if ! unzip -qt "$IPA" >/dev/null 2>&1; then
  err "downloaded .ipa is not a valid archive — refusing to publish"; exit 1
fi

# ── publish atomically ───────────────────────────────────────────────────────
mkdir -p "$DEST" || { err "cannot create $DEST"; exit 1; }
# Same-filesystem temp + mv so the backend never serves a half-written file.
cp "$IPA" "$DEST/.ManhwaManiacs.ipa.tmp" && mv -f "$DEST/.ManhwaManiacs.ipa.tmp" "$DEST/ManhwaManiacs.ipa" || {
  err "failed to write $DEST/ManhwaManiacs.ipa"; exit 1; }

# The metadata names the version the manifest advertises, so it is published
# *after* the binary: a crash between the two leaves phones briefly seeing the
# old version number (nothing offered, corrected on the next run), whereas the
# reverse order would offer an update that hands back the previous .ipa.
META="$(find "$TMP/unpacked" -name 'ios-build.json' -type f | head -1)"
if [ -n "$META" ] && python3 -m json.tool "$META" >/dev/null 2>&1; then
  cp "$META" "$DEST/.ios-build.json.tmp" && mv -f "$DEST/.ios-build.json.tmp" "$DEST/ios-build.json" || {
    err "failed to write $DEST/ios-build.json"; exit 1; }
else
  warn "no valid ios-build.json in the artifact — the manifest will fall back to"
  warn "pubspec numbers, which will not advertise this build as an update"
fi

echo "$RUN_ID" > "$STAMP"
# Match the APK drop's ownership so the container (uid 1000) can read it.
chown -R 1000:1000 "$DEST" 2>/dev/null || true

size="$(stat -c%s "$DEST/ManhwaManiacs.ipa" 2>/dev/null || echo '?')"
say "published $DEST/ManhwaManiacs.ipa ($size bytes, commit $RUN_SHA)"
if [ -r "$DEST/ios-build.json" ]; then
  advertised="$(python3 -c '
import json, sys
m = json.load(open(sys.argv[1]))
print(m.get("version", "?"), "build", m.get("buildVersion", "?"))
' "$DEST/ios-build.json" 2>/dev/null)" || advertised="(unreadable)"
  say "SideStore will advertise $advertised"
fi
