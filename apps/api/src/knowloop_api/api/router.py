from fastapi import APIRouter

from knowloop_api.api.routes.query import create_query_router
from knowloop_api.api.routes.sources import create_sources_router
from knowloop_api.api.routes.system import create_system_router
from knowloop_api.core.config import Settings


def create_api_router(settings: Settings) -> APIRouter:
    api_router = APIRouter()
    api_router.include_router(create_system_router(settings))
    api_router.include_router(create_query_router(settings))
    api_router.include_router(create_sources_router(settings))
    return api_router
