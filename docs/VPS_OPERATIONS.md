# Running ManhwaManiacs on the VPS

Live since 2026-09-03 on the OVH box in Vint Hill that also runs the Minecraft
bots. This is the operator's page: where things are, how to ship a change, and
what has to be done by hand.

| | |
|---|---|
| Web | https://manhwamaniacs.xyz (`www` 308s to the apex) |
| Install surface | https://app.manhwamaniacs.xyz — landing page, APK, `/app/source.json` for SideStore |
| Host | `ubuntu@135.148.43.147` — key auth, passwordless sudo, in the `docker` group |
| Code | `/srv/manhwamaniacs/app` — rsynced, **no `.git`** (this laptop has no GitHub push auth yet) |
| State | `/srv/manhwamaniacs/data` — the metadata SQLite DB + `settings.json`, on a dedicated 50 GB disk (`/dev/sdb1`, in fstab by UUID) |
| Artifacts | `/srv/manhwamaniacs/apk` and `/srv/manhwamaniacs/ipa`, mounted read-only into the backend |
| Containers | `manhwamaniacs-backend` (FastAPI :8000) · `manhwamaniacs-frontend` (Next standalone :3000) |
| Backups | OVH Automated Backup (Standard), daily |

## Shipping a change

From the laptop:

```bash
ops/vps/push.sh            # everything: verify the Next build locally, rsync, rebuild there
ops/vps/push.sh frontend   # or just one side
ops/vps/push.sh backend
ops/vps/push.sh apk        # publish mobile/build/.../app-release.apk to the app subdomain
```

`push.sh` builds the frontend locally first on purpose — the VPS has 2 vCores
behind a tunnel, and it is a slow place to discover a type error. The commit id
travels across in `.deploy-info` so a running container can still be traced to a
revision despite the missing `.git`.

On the VPS itself:

```bash
cd /srv/manhwamaniacs/app
bash ops/vps/deploy.sh deploy            # build + up + health gate
bash ops/vps/deploy.sh logs
bash ops/vps/deploy.sh edge              # re-apply the Caddy vhosts + tunnel ingress (idempotent)
bash ops/vps/deploy.sh create-owner      # needs a TTY: ssh -t
bash ops/vps/deploy.sh install-timers    # one-off: install + enable the iOS-build-fetch systemd timer
```

## How traffic reaches it

Nothing is published on a host port. The **Minecraft stack's** Caddy and
cloudflared do the edge work — this app joins their `mcbots_bots` network as a
co-tenant rather than standing up a second proxy or a second tunnel:

```
Cloudflare ──tunnel e40ede74-…(mcbots-vinthill)──▶ cloudflared ──▶ caddy:80 ──▶ manhwamaniacs-frontend:3000
                                                                          └──▶ manhwamaniacs-backend:8000   (app. subdomain)
```

Config lives with the Minecraft stack: `/opt/mcbots/edge/Caddyfile` and
`/opt/mcbots/edge/cloudflared/config.yml`. `deploy.sh edge` appends to both and
keeps timestamped `.bak-mm-*` copies. DNS is three proxied CNAMEs (`@`, `www`,
`app`) pointing at `e40ede74-c9c0-454d-9983-3a6ce2866a47.cfargotunnel.com`.

**Do not** add a second tunnel or a second Caddy. Touching the shared files means
the bots share the blast radius — check `minecraft.yashnas.xyz` still answers
after any edge change.

## Manual steps that are not automated

1. **Cloudflare Browser Cache TTL must be "Respect Existing Headers".** It is
   currently 4 hours, which overrides the origin on `/sw.js`: the origin
   correctly sends `no-cache, must-revalidate`, Cloudflare rewrites it to
   `max-age=14400`, and a browser then holds a stale **service worker** — the
   thing that controls the whole app shell and the offline store — for up to
   four hours, with no way for the reader to clear it themselves. Fix at
   *Caching → Configuration → Browser Cache TTL*, or with a Cache Rule that
   bypasses `/sw.js`, `/sw-policy.js`, `/offline-fallback.html`.
2. **GitHub push auth.** This laptop cannot push (`git@github.com: Permission
   denied (publickey)`), so the cloud-Mac iOS build never runs. Add the laptop
   key to the account, or use a PAT.
3. **Repo visibility.** The IPA sync downloads *release assets anonymously*,
   which needs a public repo. The repo currently reads Private — either make it
   public or put a token with `Actions:read` at `/root/.gh_token` on the VPS.
4. **The iOS sync timer.** `ops/vps/deploy.sh install-timers` installs a
   15-minute systemd timer that runs `ops/fetch-ios-build.sh` (idempotent, run
   it again after any deploy). There is still nothing for it to fetch until 2
   and 3 above are resolved — a missing release just means each run exits 2
   ("nothing new to publish").

## Accounts

One account exists: `Yash`, admin, created through the web bootstrap form.
`MM_REGISTRATION_ENABLED=false`, so `needs_bootstrap` is false and nobody else
can register. **An empty users table on a public host is an open admin
takeover** — if the DB is ever wiped, create the owner before DNS points at it.

## Disk

The system disk (`/dev/sda`, 40 GB) holds the OS, Docker, and the Minecraft
stack; ~27 GB free after a prune of 16.5 GB of stale Rust build cache. The
manhwamaniacs disk (`/dev/sdb1`, 50 GB at `/srv/manhwamaniacs`) is essentially
empty and stays that way by design: **chapter images never touch the server.**
If disk use there starts climbing, something has regressed.
