"""Endpoint-level tests for session, chat and confirmation control flow."""
import json

from fastapi.responses import JSONResponse

from data import PENDING_REFUNDS, REFUNDS_INITIATED
from server import (
    ChatRequest,
    SessionRequest,
    _contexts,
    _sessions,
    chat,
    confirm_refund,
    create_session,
    reset_session,
)
from tools import prepare_refund


def _response_body(response: JSONResponse) -> dict:
    return json.loads(response.body)


def test_guest_session_is_server_generated():
    result = create_session(SessionRequest(mode="guest"))
    assert result["session_id"] in _sessions
    assert result["authenticated"] is False
    assert _contexts[result["session_id"]].customer_id is None


def test_sarah_demo_session_uses_fixed_customer_context():
    result = create_session(SessionRequest(mode="sarah_demo"))
    ctx = _contexts[result["session_id"]]
    assert result["customer_name"] == "Sarah Lee"
    assert ctx.authenticated is True
    assert ctx.customer_id == "CUST-004"


def test_chat_rejects_unknown_session():
    response = chat(ChatRequest(message="Hello", session_id="unknown"))
    assert isinstance(response, JSONResponse)
    assert response.status_code == 404


def test_chat_returns_pending_refund_without_exposing_token(monkeypatch):
    session = create_session(SessionRequest(mode="sarah_demo"))
    session_id = session["session_id"]
    prepare_refund("BK-10105", _contexts[session_id])
    monkeypatch.setattr(_sessions[session_id], "reply", lambda _: "Please confirm.")

    result = chat(ChatRequest(message="Damaged delivery", session_id=session_id))

    assert result["confirmation_required"] is True
    assert result["pending_refund"]["order_id"] == "BK-10105"
    assert "token" not in result["pending_refund"]


def test_confirmation_executes_refund_once():
    session = create_session(SessionRequest(mode="sarah_demo"))
    session_id = session["session_id"]
    prepare_refund("BK-10105", _contexts[session_id])

    first = confirm_refund(session_id)
    second = confirm_refund(session_id)

    assert first["success"] is True
    assert first["status"] == "initiated"
    assert second["status"] == "already_initiated"
    assert len(REFUNDS_INITIATED) == 1


def test_confirmation_requires_pending_refund():
    session = create_session(SessionRequest(mode="sarah_demo"))
    response = confirm_refund(session["session_id"])
    assert isinstance(response, JSONResponse)
    assert response.status_code == 404


def test_guest_cannot_confirm_refund():
    session = create_session(SessionRequest(mode="guest"))
    response = confirm_refund(session["session_id"])
    assert isinstance(response, JSONResponse)
    assert response.status_code == 403
    assert "sign in" in _response_body(response)["error"].lower()


def test_reset_removes_session_context_and_pending_refund():
    session = create_session(SessionRequest(mode="sarah_demo"))
    session_id = session["session_id"]
    prepare_refund("BK-10105", _contexts[session_id])

    assert reset_session(session_id) == {"ok": True}
    assert session_id not in _sessions
    assert session_id not in _contexts
    assert not PENDING_REFUNDS


def test_chat_enforces_message_length_limit():
    session = create_session(SessionRequest(mode="guest"))
    response = chat(ChatRequest(message="x" * 4001, session_id=session["session_id"]))
    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
    assert "character limit" in _response_body(response)["error"]
