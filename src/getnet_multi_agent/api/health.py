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
    ingesting = request.app.state.ingest_status == "running"  # partial collection is not ready
    if chunks > 0 and db_ok and not ingesting:
        return {"status": "ready", "chunks": chunks}
    reason = ("database unavailable" if not db_ok else
              f"knowledge base not ready ({request.app.state.ingest_status}, {chunks} chunks)")
    return JSONResponse(status_code=503, content={"status": "not_ready", "reason": reason})
