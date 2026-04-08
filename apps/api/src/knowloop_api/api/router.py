from fastapi import APIRouter

from knowloop_api.api.routes.system import create_system_router
from knowloop_api.core.config import Settings


def create_api_router(settings: Settings) -> APIRouter:
    api_router = APIRouter()
    api_router.include_router(create_system_router(settings))
    return api_router
