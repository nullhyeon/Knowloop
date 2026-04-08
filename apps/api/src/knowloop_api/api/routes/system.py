from fastapi import APIRouter

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
def system_health() -> dict[str, str]:
    return {"status": "ok"}
