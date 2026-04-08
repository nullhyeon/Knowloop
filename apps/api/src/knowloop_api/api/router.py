from fastapi import APIRouter

from knowloop_api.api.routes.system import router as system_router

api_router = APIRouter()
api_router.include_router(system_router)
