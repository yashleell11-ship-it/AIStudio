from __future__ import annotations

from fastapi import APIRouter, Depends

from routes.app_distribution import router as app_distribution_router
from routes.auth import router as auth_router
from routes.backup import router as backup_router
from routes.downloads import router as downloads_router
from routes.library import router as library_router
from routes.ocr import router as ocr_router
from routes.reader import router as reader_router
from routes.sources import router as sources_router
from routes.settings import router as settings_router
from routes.system import router as system_router
from routes.updates import router as updates_router
from services.auth_service import enforce_authentication

# Every route on the API requires a valid session except the public allowlist
# defined in enforce_authentication (health/landing, APK distribution, and the
# login/register entry points). This is the single global authentication gate.
api_router = APIRouter(dependencies=[Depends(enforce_authentication)])
api_router.include_router(system_router)
api_router.include_router(app_distribution_router)
api_router.include_router(auth_router)
api_router.include_router(backup_router)
api_router.include_router(settings_router)
api_router.include_router(library_router)
api_router.include_router(downloads_router)
api_router.include_router(reader_router)
api_router.include_router(sources_router)
api_router.include_router(ocr_router)
api_router.include_router(updates_router)
