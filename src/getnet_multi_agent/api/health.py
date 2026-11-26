from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health/live")
def live(request: Request):
    return {"status": "live", "rev": request.app.state.settings.APP_REV}


@router.get("/health/ready")
def ready(request: Request):
    from getnet_multi_agent.rag import store

    s = request.app.state.settings
    chunks = store.count(s)
    db_ok = request.app.state.db.ping()
    if chunks > 0 and db_ok:
        return {"status": "ready", "chunks": chunks}
    reason = "database unavailable" if not db_ok else f"knowledge base empty ({request.app.state.ingest_status})"
    return JSONResponse(status_code=503, content={"status": "not_ready", "reason": reason})
