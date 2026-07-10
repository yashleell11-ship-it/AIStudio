# ManhwaManiacs

Self-hosted manga/manhwa reader and multi-source aggregator: a FastAPI backend (content
connectors + download/library management), a Next.js web frontend, and a Flutter mobile app.

> **Canonical home:** this repo lives on the NAS at `/home/yash/dev/aistudio` and is
> version-controlled in Forgejo (`git.yashnas.xyz/yash/aistudio`). Develop on the NAS —
> see the platform docs in `/srv`: `DEV-WORKFLOW.md`, `REMOTE-ACCESS.md`, `DISASTER-RECOVERY.md`.

## Layout
```
backend/    Python 3.11+ API + CLI ("manhwamaniacs-backend")
            api/ routes/ services/ connectors/{mangadex,mangakatana,toonily,...}
            core/ database/ main.py cli.py   (see pyproject.toml)
frontend/   Next.js 16 / React 19 web app   (npm run dev|build|start)
mobile/     Flutter app                     (pubspec.yaml)
docs/       project documentation
```
Runtime/local dirs `library/`, `memory/`, `config/` are gitignored (local data, not source).

## Remotes
```
origin  ssh://git@192.168.1.2:2222/yash/aistudio.git       # Forgejo (canonical)
github  https://github.com/yashleell11-ship-it/AIStudio     # backup mirror
```

## Quickstart
```
# Backend
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -e .
# Frontend
cd frontend && npm install && npm run dev
# Mobile: build with the Flutter SDK on a workstation
```

## Workflow
Branch from `master` (`feat/<name>`), commit, `git push`. Full guide: `/srv/DEV-WORKFLOW.md`.
