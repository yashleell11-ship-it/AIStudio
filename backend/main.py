from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.router import api_router
from connectors.registry import log_registered_connectors, validate_registry
from core.config import get_settings
from core.errors import register_error_handlers
from database.session import SessionLocal, init_db
from services.download_manager import get_download_manager
from services.ocr_pipeline import get_ocr_manager
from services.update_scheduler import get_update_manager
from services.import_cleanup import ImportCleanupService


def run_startup_migrations() -> None:
    init_db()
    db = SessionLocal()
    try:
        ImportCleanupService(db).merge_all_orphans_global()
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_app(*, run_migrations: bool = True, run_workers: bool = True) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if run_migrations:
            run_startup_migrations()
        else:
            init_db()
        manager = get_download_manager()
        ocr_manager = get_ocr_manager()
        update_manager = get_update_manager()
        if run_workers:
            manager.start()
            ocr_manager.start()
            update_manager.start()
        startup_logger = logging.getLogger("uvicorn.error")
        validate_registry()
        log_registered_connectors(startup_logger)
        _log_registered_routes(_app)
        yield
        if run_workers:
            manager.stop()
            ocr_manager.stop()
            update_manager.stop()

    app = FastAPI(
        title="AIStudio Backend",
        version=settings.version,
        description="AIStudio backend API for manhwa library management",
        docs_url="/docs",
        redoc_url="/redoc",
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
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
