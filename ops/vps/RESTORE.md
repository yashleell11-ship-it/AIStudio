# ManhwaManiacs — database backup & restore runbook

The database is the only copy of every account, reading profile, follow,
progress row and bookmark. Chapter images are never stored server-side, so
this file *is* the product.

| file | what it is |
|---|---|
| `ops/vps/backup-db.sh` | the backup itself: `run`, `verify`, `list`, `stage-restore` |
| `ops/vps/deploy.sh install-timers` | writes `mm-db-backup.{service,timer}` and enables them; `cmd_deploy` calls it, so every push re-installs them |
| `/srv/manhwamaniacs/backups/` | where snapshots land, on the 49 GB `/srv` disk (never the root disk) |

## What the backup is

`backup-db.sh run` (nightly 03:30 UTC via `mm-db-backup.timer`, as `ubuntu`):

1. `VACUUM INTO` from a `?mode=ro` connection of the **host** `python3`
   (sqlite 3.46.1) straight on `/srv/manhwamaniacs/data/manhwamaniacs.db`.
   Consistent under WAL, never blocks the app's writers, never checkpoints,
   never writes to the live file. Same primitive the admin "export" button
   uses (`backend/services/backup_service.py:59`). Verified on the live box:
   0.09 s for the 21 MB DB, copy integrity_check ok, gzip ≈ 10 MB.
2. fsync the copy (SQLite does not fsync a VACUUM INTO target).
3. `PRAGMA integrity_check` + `foreign_key_check` **on the copy**; a bad copy
   is discarded and the run fails loudly (systemd unit → failed).
4. `zstd -9`, atomic `mv` into `/srv/manhwamaniacs/backups/daily/`, `sync -f`.
5. Rotation: 7 daily; on Sundays (or when `weekly/` is empty) hard-link into
   `weekly/`, keep 4. `latest.db.zst` symlink → newest daily.
6. One log line per run in `backups/backup.log` and the journal:
   status, file, compressed bytes, elapsed, total bytes on disk, and a JSON
   blob with alembic revision, uncompressed size, live `.db`/`-wal` sizes,
   FK violations and row counts of users / reading_profiles / followed_series /
   chapter_progress / bookmarks — so a silent data-loss regression shows up as
   a count that drops.

Free-space guard: refuses to run with less than 3 × (db + wal) free on the
backup disk. Lock: `flock` on `backups/.lock`.

Budget on the current DB: ~10 MB × 11 files ≈ 110 MB on a disk with 47 GB free.

## Install (once, after the patch lands)

```sh
ssh ubuntu@135.148.43.147
cd /srv/manhwamaniacs/app && bash ops/vps/deploy.sh install-timers   # or just: deploy
systemctl list-timers mm-db-backup.timer --no-pager
sudo systemctl start mm-db-backup.service && journalctl -u mm-db-backup -n 3 --no-pager
ops/vps/backup-db.sh list
```

## Verify (monthly drill — a backup nobody has restored is a hope, not a backup)

```sh
ops/vps/backup-db.sh verify                  # newest
ops/vps/backup-db.sh verify /srv/manhwamaniacs/backups/weekly/<file>.db.zst
```
Decompresses to a temp dir, runs `integrity_check`, prints revision + counts,
removes the temp dir. Never touches the live DB.

## Restore

The backend already has a staged-restore mechanism: a file at
`<db>.pending-restore` is swapped in on the next process start, before any
connection is opened (`backend/main.py:10`, `backend/core/backup_restore.py:32`).
Use it instead of copying over the live file by hand.

```sh
cd /srv/manhwamaniacs/app
MM_CONFIRM=RESTORE ops/vps/backup-db.sh stage-restore /srv/manhwamaniacs/backups/daily/<file>.db.zst
#  -> takes a fresh backup FIRST (your undo), verifies the chosen file,
#     writes /srv/manhwamaniacs/data/manhwamaniacs.db.pending-restore
docker restart manhwamaniacs-backend
docker logs --since 2m manhwamaniacs-backend | grep -i restore
#  expect: "Applied a staged database restore before startup."
```

Abort before the restart: `rm -f /srv/manhwamaniacs/data/manhwamaniacs.db.pending-restore`
(or `DELETE /api/backup/pending` from the admin UI).
Undo after the restart: stage-restore the `latest.db.zst` that step 1 produced.

Two things the app's restore path does NOT do today (see audit findings; fix
in `backend/`, not here):
- it keeps no copy of the file it overwrites — hence the mandatory pre-restore
  backup above;
- it does not check the file's `alembic_version` against the code's head — a
  backup taken from a *newer* build than the one running crash-loops the
  container at startup (`Can't locate revision identified by ...`) with the
  old DB already gone. Deploy the matching (or newer) code first, then restore.

### Bare-metal restore (container gone, disk replaced)

```sh
sudo mkdir -p /srv/manhwamaniacs/data && sudo chown 1000:1000 /srv/manhwamaniacs/data
zstd -d /path/to/manhwamaniacs-<stamp>.db.zst -o /srv/manhwamaniacs/data/manhwamaniacs.db
sudo chown 1000:1000 /srv/manhwamaniacs/data/manhwamaniacs.db
rm -f /srv/manhwamaniacs/data/manhwamaniacs.db-wal /srv/manhwamaniacs/data/manhwamaniacs.db-shm
cd /srv/manhwamaniacs/app && bash ops/vps/deploy.sh      # migrations run at startup
```
The snapshot is a rollback-journal file (`journal_mode=delete`); the app's
first connection flips it back to WAL (`backend/database/session.py:39`).

## Off-box copy (recommended follow-up, not in this proposal)

Everything above is on the same VPS. Disk loss or a compromised box takes
the backups with it. Cheapest next step, from the laptop that already has
SSH (this machine), pulled — so the VPS never holds a credential to anything:

```sh
rsync -az ubuntu@135.148.43.147:/srv/manhwamaniacs/backups/weekly/ ~/backups/manhwamaniacs/
```
(cron/systemd --user on the laptop; or `rclone copy` of `backups/` to a
Cloudflare R2 bucket from the VPS if a push model is preferred.)

## Related maintenance the DB never gets today

Evidence from the live box (read-only, 2026-09-06):
- `wal_autocheckpoint=1000` (default); `.db` mtime 08:28:58 (the deploy
  restart), `-wal` last written 14:29:05 and unchanged through 15:21 at
  313 152 B (≈76 frames). At this write rate the WAL only checkpoints on a
  restart; that is harmless for SQLite, but it is why a naive `cp` of the
  `.db` is not a backup.
- `PRAGMA optimize` / `ANALYZE` never run (grep of backend/: no hits), so the
  planner has no `sqlite_stat1` for the 28 tables.
- `freelist_count=3` — no bloat; `VACUUM` is not needed (and the nightly
  snapshot is compacted anyway).

Proposed in-app addition (backend, small): once a day from the existing
`services/update_scheduler.py` thread, on a dedicated connection:
`PRAGMA optimize;` then `PRAGMA wal_checkpoint(PASSIVE);` — cheap, and keeps
the main file fresh so the on-disk `.db` is never hours behind.

## Root disk: what the 30 GB is and what is safe to reclaim

Measured (read-only) 2026-09-06 on `/dev/sda1` 38 G, 30 G used, 7.8 G free:

| what | size | safe action | reclaims |
|---|---|---|---|
| Docker **build cache** (`docker system df`: 169 entries, 18.78 GB, **18.59 GB reclaimable**, 0 in use; seven ~994 MB layers from the last 40 h of `compose build` runs, the biggest ones from the recall-frontend image) | 18.8 GB | `docker builder prune -af --filter until=24h` (or `--keep-storage 3GB`) — only cost is one slower rebuild | ~18 GB |
| `/var/lib/containerd` (Docker 29 containerd image store: images 4.87 GB + the cache above) | 21 GB | covered by the prune; then `docker image prune -f` for the 37 MB dangling | 37 MB |
| `~/.vscode-server/cli/servers` — 5 stale VS Code Remote server builds × ~700 MB | 3.5 GB | delete all but the newest `Stable-*` dir (VS Code re-downloads if wrong) | ~2.8 GB |
| systemd journal | 319 MB | `sudo journalctl --vacuum-size=100M` | ~200 MB |
| mcbots container logs (`*-json.log.{1..4}` at 20 MB each, several containers) | ~200 MB | already capped by their logging opts; leave | 0 |
| `/usr` | 2.6 GB | leave | 0 |

Expected result: ~9 GB used → ~24 %. Add `docker builder prune -f --filter
until=72h` at the end of `cmd_deploy` in `ops/vps/deploy.sh` so the cache
stops accreting 2 GB per push (the manhwamaniacs build itself is ~0.5 GB of
layers; the rest is the co-tenant recall project's).
