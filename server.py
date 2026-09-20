"""
FastAPI server — wraps SupportAgent behind a /chat endpoint
and serves the browser UI from static/index.html.

Run:  uvicorn server:app --reload
      then open http://127.0.0.1:8000

Prototype note: sessions are stored in-memory and lost on restart.
Production deployments require a durable session store.
"""
import json
import pathlib
import secrets
from typing import Literal

from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from agent import SupportAgent
from config import settings
from context import CustomerContext
from data import PENDING_REFUNDS
from tools import initiate_refund

app = FastAPI(title="Bookly AI Concierge")

# In-memory session stores — prototype only
_sessions: dict[str, SupportAgent] = {}
_contexts: dict[str, CustomerContext] = {}

_UI = pathlib.Path(__file__).parent / "static" / "index.html"


class ChatRequest(BaseModel):
    message: str
    session_id: str


class SessionRequest(BaseModel):
    mode: Literal["guest", "sarah_demo"] = "guest"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _UI.read_text(encoding="utf-8")


@app.post("/session")
def create_session(req: SessionRequest | None = Body(default=None)) -> dict:
    """Create a server-generated session for one of the fixed demo profiles."""
    mode = req.mode if req else "guest"
    session_id = secrets.token_urlsafe(16)
    if mode == "sarah_demo":
        ctx = CustomerContext(
            session_id=session_id,
            authenticated=True,
            customer_id="CUST-004",
        )
        customer_name = "Sarah Lee"
    else:
        ctx = CustomerContext(session_id=session_id, authenticated=False)
        customer_name = None

    _contexts[session_id] = ctx
    _sessions[session_id] = SupportAgent(ctx=ctx)
    return {
        "session_id": session_id,
        "mode": mode,
        "authenticated": ctx.authenticated,
        "customer_name": customer_name,
    }


@app.post("/chat")
def chat(req: ChatRequest):
    # Validate message length
    if len(req.message) > settings.MAX_MESSAGE_LENGTH:
        return JSONResponse(
            status_code=400,
            content={
                "error": (
                    f"Message exceeds the {settings.MAX_MESSAGE_LENGTH} character limit."
                )
            },
        )

    # Require a valid server-generated session
    if req.session_id not in _sessions:
        return JSONResponse(
            status_code=404,
            content={"error": "Session not found. Call POST /session first."},
        )

    agent = _sessions[req.session_id]

    # Validate conversation turn count (each turn = 2 history entries: user + assistant)
    if len(agent._client.history) >= settings.MAX_CONVERSATION_TURNS * 2:
        return JSONResponse(
            status_code=400,
            content={"error": "Conversation limit reached. Please start a new session."},
        )

    reply = agent.reply(req.message)
    pending = _pending_refund_for_session(req.session_id, include_consumed=False)
    return {
        "reply": reply,
        "tool_calls": agent.last_tool_calls,
        "session_id": req.session_id,
        "confirmation_required": pending is not None,
        "pending_refund": _public_refund_summary(pending),
    }


@app.post("/confirm/{session_id}")
def confirm_refund(session_id: str):
    """Application-controlled confirmation endpoint.

    Looks up the pending refund for the session and calls initiate_refund with
    the stored token.  The token is never exposed to or passed by the LLM.
    """
    ctx = _contexts.get(session_id)
    if not ctx:
        return JSONResponse(status_code=404, content={"error": "Session not found."})

    if not ctx.authenticated or not ctx.customer_id:
        return JSONResponse(
            status_code=403,
            content={"error": "Sign in is required to confirm a refund."},
        )

    pending_entry = _pending_refund_for_session(session_id, include_consumed=True)

    if not pending_entry:
        return JSONResponse(
            status_code=404,
            content={"error": "No pending refund found for this session."},
        )

    token, pending_data = pending_entry
    result = json.loads(initiate_refund(pending_data["order_id"], ctx, token))
    return result


@app.delete("/session/{session_id}")
def reset_session(session_id: str) -> dict:
    agent = _sessions.pop(session_id, None)
    _contexts.pop(session_id, None)
    for token, pending in list(PENDING_REFUNDS.items()):
        if pending["session_id"] == session_id:
            PENDING_REFUNDS.pop(token, None)
    if agent:
        agent.reset()
    return {"ok": True}


def _pending_refund_for_session(
    session_id: str,
    *,
    include_consumed: bool,
) -> tuple[str, dict] | None:
    """Return the most recent pending refund for a session without exposing its token."""
    entries = list(PENDING_REFUNDS.items())
    for token, pending in reversed(entries):
        if pending["session_id"] != session_id:
            continue
        if not include_consumed and pending.get("consumed"):
            continue
        return token, pending
    return None


def _public_refund_summary(entry: tuple[str, dict] | None) -> dict | None:
    if not entry:
        return None
    _, pending = entry
    return {
        "order_id": pending["order_id"],
        "amount": pending["amount"],
        "payment_destination": pending["payment_destination"],
    }
