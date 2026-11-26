from fastapi import APIRouter

from getnet_multi_agent.core.settings import get_settings

router = APIRouter()


@router.get("/health/live")
def live():
    return {"status": "live", "rev": get_settings().APP_REV}


@router.get("/health/ready")
def ready():
    return {"status": "ready", "chunks": 0}
