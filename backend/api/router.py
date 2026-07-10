from __future__ import annotations

from fastapi import APIRouter

from routes.app_distribution import router as app_distribution_router
from routes.backup import router as backup_router
from routes.downloads import router as downloads_router
from routes.library import router as library_router
from routes.ocr import router as ocr_router
from routes.reader import router as reader_router
from routes.sources import router as sources_router
from routes.settings import router as settings_router
from routes.system import router as system_router
from routes.updates import router as updates_router

api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(app_distribution_router)
api_router.include_router(backup_router)
api_router.include_router(settings_router)
api_router.include_router(library_router)
api_router.include_router(downloads_router)
api_router.include_router(reader_router)
api_router.include_router(sources_router)
api_router.include_router(ocr_router)
api_router.include_router(updates_router)
