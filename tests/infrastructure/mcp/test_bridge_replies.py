"""What the bridge owes its client, and what it says when the backend cannot answer.

The obligation is per-id: a request is outstanding from the moment it is forwarded until a reply for
*that id* comes back. These are the cases the five-hour hang was made of — a forwarded request whose
answer never arrived, with nothing recording that anything was owed.
"""

from __future__ import annotations

import pytest
from mcp.types import (
    CONNECTION_CLOSED,
    ErrorData,
    JSONRPCError,
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)

from src.infrastructure.mcp.bridge_replies import OutstandingReplies, failure_reason


def _request(request_id: int | str, method: str = "tools/list") -> JSONRPCMessage:
    return JSONRPCMessage(JSONRPCRequest(jsonrpc="2.0", id=request_id, method=method))


def _response(request_id: int | str) -> JSONRPCMessage:
    return JSONRPCMessage(JSONRPCResponse(jsonrpc="2.0", id=request_id, result={}))


def _error(request_id: int | str) -> JSONRPCMessage:
    return JSONRPCMessage(
        JSONRPCError(jsonrpc="2.0", id=request_id, error=ErrorData(code=-32603, message="no"))
    )


def test_a_forwarded_request_is_owed_an_answer() -> None:
    outstanding = OutstandingReplies()
    outstanding.accept(_request(7, "artifact_verify"))

    (reply,) = outstanding.as_connection_closed("ConnectError: refused")
    assert isinstance(reply.root, JSONRPCError)
    assert reply.root.id == 7
    assert reply.root.error.code == CONNECTION_CLOSED
    # Both halves are needed to act on it: which call died, and why.
    assert "artifact_verify" in reply.root.error.message
    assert "ConnectError: refused" in reply.root.error.message


def test_an_answered_request_is_owed_nothing() -> None:
    outstanding = OutstandingReplies()
    outstanding.accept(_request(1))
    outstanding.settle(_response(1))

    assert outstanding.as_connection_closed("gone") == ()


def test_a_backend_error_settles_the_request_too() -> None:
    """An error *is* an answer; re-answering it would deliver two replies for one id."""
    outstanding = OutstandingReplies()
    outstanding.accept(_request(1))
    outstanding.settle(_error(1))

    assert outstanding.as_connection_closed("gone") == ()


def test_only_the_unanswered_ids_are_answered() -> None:
    outstanding = OutstandingReplies()
    for request_id in (1, 2, 3):
        outstanding.accept(_request(request_id, f"call_{request_id}"))
    outstanding.settle(_response(2))

    answered = {reply.root.id for reply in outstanding.as_connection_closed("gone")}
    assert answered == {1, 3}


def test_string_ids_are_kept_as_given() -> None:
    """JSON-RPC ids may be strings, and an answer addressed to a coerced id answers nobody."""
    outstanding = OutstandingReplies()
    outstanding.accept(_request("call-abc"))

    (reply,) = outstanding.as_connection_closed("gone")
    assert reply.root.id == "call-abc"


def test_a_notification_is_owed_nothing() -> None:
    outstanding = OutstandingReplies()
    outstanding.accept(JSONRPCMessage(JSONRPCNotification(jsonrpc="2.0", method="notifications/initialized")))

    assert outstanding.as_connection_closed("gone") == ()


def test_an_unknown_id_settles_without_complaint() -> None:
    """A reply the bridge has no record of is the backend's business, not a reason to fail."""
    outstanding = OutstandingReplies()
    outstanding.settle(_response(99))

    assert outstanding.as_connection_closed("gone") == ()


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (ValueError("bad json"), "ValueError: bad json"),
        (RuntimeError(), "RuntimeError"),
        (ExceptionGroup("group", [ConnectionError("refused")]), "ConnectionError: refused"),
        (
            ExceptionGroup("group", [ExceptionGroup("inner", [OSError("closed")]), ValueError("x")]),
            "OSError: closed; ValueError: x",
        ),
    ],
)
def test_a_failure_reads_as_one_line(failure: BaseException, expected: str) -> None:
    """A task group reports an `ExceptionGroup`; a client log needs the cause inside it."""
    assert failure_reason(failure) == expected
