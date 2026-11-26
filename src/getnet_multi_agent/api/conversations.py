from fastapi import APIRouter, Depends, HTTPException, Request

from getnet_multi_agent.contracts import Principal
from getnet_multi_agent.security.auth import require_merchant
from getnet_multi_agent.state import conversations as conv

router = APIRouter()


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, request: Request,
                     principal: Principal = Depends(require_merchant)):
    db = request.app.state.db
    if conv.get_conversation(db, conversation_id, principal.sub) is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "conversation not found"})
    turns = [{k: t[k] for k in ("role", "text", "route", "status", "sources", "created_at")}
             for t in conv.list_turns(db, conversation_id)]
    return {"id": conversation_id, "turns": turns}
