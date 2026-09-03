# ManhwaManiacs

Self-hosted manga/manhwa reader and multi-source aggregator, for a small
household of real accounts (each with Netflix-style reading profiles). Three
clients — a Next.js web app, a Flutter mobile app, and the raw API — over a
FastAPI + SQLite backend. Deployed on a single VPS with a deliberately small
disk budget: the server scrapes metadata and proxies page images on demand,
but **never stores a chapter on disk** — anything kept for offline reading
lives on the client (browser Cache Storage on web, on-device SQLite + blobs
on mobile).

Live at https://manhwamaniacs.xyz · app/install at https://app.manhwamaniacs.xyz

Start here: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — the whole
system on one page, with links out to the deeper docs.

## Layout

```
backend/    FastAPI + SQLAlchemy API ("manhwamaniacs-backend")
            connectors/{mangadex,toonily,...} routes/ services/ core/ database/
frontend/   Next.js 16 / React 19 web app        (npm run dev|build|start)
mobile/     Flutter app (Android + sideloaded iOS)   (pubspec.yaml)
docs/       project documentation — see docs/ARCHITECTURE.md first
ops/vps/    VPS deploy: docker-compose.yml, deploy.sh (VPS), push.sh (laptop)
```
Runtime/local dirs `library/` and `config/` are gitignored (local data, not source).

## Quickstart (local dev)

```bash
# Backend
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -e .
uvicorn main:app --reload    # http://127.0.0.1:8000, docs at /docs

# Frontend
cd frontend && npm install && npm run dev    # http://localhost:3000

# Mobile: build with the Flutter SDK; --dart-define=API_URL=http://127.0.0.1:8000
```

Registration is closed by default outside of a fresh empty database — see
[docs/AUTH.md](docs/AUTH.md) for the bootstrap/invite-code flow.

## Deploying

Production is one VPS (Ubuntu, OVH), reached from a laptop that has no direct
git push access to it — code ships by rsync, not `git pull`:

```bash
ops/vps/push.sh              # build, sync, rebuild everything
ops/vps/push.sh frontend     # or just one side
ops/vps/push.sh backend
ops/vps/push.sh apk          # publish a built Android release APK
```

Full operator's page: [docs/VPS_OPERATIONS.md](docs/VPS_OPERATIONS.md).

## Docs

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) is the map. From there:
[AUTH.md](docs/AUTH.md), [OFFLINE_READING.md](docs/OFFLINE_READING.md),
[SOURCES.md](docs/SOURCES.md), [VPS_OPERATIONS.md](docs/VPS_OPERATIONS.md),
[ROADMAP.md](docs/ROADMAP.md), and the pivot specs under
[docs/superpowers/specs/](docs/superpowers/specs/).
