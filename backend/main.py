from __future__ import annotations

# Must run before any other backend import: if a restore was staged (see
# core.backup_restore / routes.backup), this swaps the database file in on
# disk before database.session ever opens (and process-lifetime caches) a
# connection to it. core.backup_restore is stdlib + core.config only, so
# importing it here can never transitively trigger database.session itself.
from core.backup_restore import apply_pending_restore_if_present

_restore_applied_on_boot = apply_pending_restore_if_present()

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.router import api_router
from connectors.registry import log_registered_connectors, validate_registry
from core.config import get_settings
from core.errors import register_error_handlers
from core.rate_limit import limiter, rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from database.session import SessionLocal, init_db
from services.auth_service import AuthService
from services.update_scheduler import get_update_manager


def prune_expired_sessions() -> None:
    """Opportunistically delete expired auth sessions at startup. Individual
    tokens are also pruned lazily when resolved, but this clears in one pass any
    backlog that accumulated while the process was down."""
    db = SessionLocal()
    try:
        removed = AuthService(db).cleanup_expired()
        if removed:
            logging.getLogger("uvicorn.error").info(
                "Pruned %d expired auth session(s) at startup.", removed
            )
    finally:
        db.close()


def create_app(*, run_migrations: bool = True, run_workers: bool = True) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if _restore_applied_on_boot:
            logging.getLogger("uvicorn.error").info(
                "Applied a staged database restore before startup."
            )
        if run_migrations:
            init_db()
            prune_expired_sessions()
        update_manager = get_update_manager()
        if run_workers:
            update_manager.start()
        startup_logger = logging.getLogger("uvicorn.error")
        validate_registry()
        log_registered_connectors(startup_logger)
        _log_registered_routes(_app)
        yield
        if run_workers:
            update_manager.stop()

    # Interactive API docs + the OpenAPI schema publish the full endpoint map
    # (including admin backup/import ops) to anonymous callers, so gate them
    # behind debug for the public, currently-unauthenticated deployment.
    _docs_enabled = bool(getattr(settings, "debug", False))
    app = FastAPI(
        title="ManhwaManiacs Backend",
        version=settings.version,
        description="ManhwaManiacs backend API for manhwa library management",
        docs_url="/docs" if _docs_enabled else None,
        redoc_url="/redoc" if _docs_enabled else None,
        openapi_url="/openapi.json" if _docs_enabled else None,
        lifespan=lifespan,
    )

    if "*" in settings.cors_origins and not getattr(settings, "debug", False):
        raise RuntimeError(
            "CORS wildcard ('*') is not permitted outside debug mode. "
            "Set CORS_ORIGINS to specific allowed origins before deploying."
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)
    # Inbound rate limiting: the limiter is referenced by the per-route
    # decorators via app.state, and a 429 is rendered in our standard envelope.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.include_router(api_router)
    return app


def _log_registered_routes(app: FastAPI) -> None:
    schema = app.openapi()
    tags: set[str] = set()
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                for tag in operation.get("tags", []):
                    tags.add(str(tag))
    tag_list = ", ".join(sorted(tags)) or "none"
    logging.getLogger("uvicorn.error").info(
        "Registered API route groups: %s (%d paths)",
        tag_list,
        len(schema.get("paths", {})),
    )


app = create_app()


def main() -> None:
    import os

    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        # Auto-reload is a dev-only convenience; never enable it in a real deploy.
        reload=os.getenv("MM_DEV_RELOAD", "").lower() in ("1", "true", "yes"),
    )


if __name__ == "__main__":
    main()
