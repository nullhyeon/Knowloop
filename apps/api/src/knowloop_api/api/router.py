from fastapi import APIRouter

from knowloop_api.api.routes.context import create_context_router
from knowloop_api.api.routes.instructor import create_instructor_router
from knowloop_api.api.routes.maintenance import create_maintenance_router
from knowloop_api.api.routes.query import create_query_router
from knowloop_api.api.routes.review import create_review_router
from knowloop_api.api.routes.sessions import create_sessions_router
from knowloop_api.api.routes.sources import create_sources_router
from knowloop_api.api.routes.system import create_system_router
from knowloop_api.api.routes.wiki import create_wiki_router
from knowloop_api.core.config import Settings


def create_api_router(settings: Settings) -> APIRouter:
    api_router = APIRouter()
    api_router.include_router(create_system_router(settings))
    api_router.include_router(create_context_router(settings))
    api_router.include_router(create_query_router(settings))
    api_router.include_router(create_review_router(settings))
    api_router.include_router(create_sessions_router(settings))
    api_router.include_router(create_sources_router(settings))
    api_router.include_router(create_instructor_router(settings))
    api_router.include_router(create_maintenance_router(settings))
    api_router.include_router(create_wiki_router(settings))
    return api_router
