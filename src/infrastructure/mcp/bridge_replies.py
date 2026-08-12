"""What a stdio bridge still owes its client, and what to say when the backend cannot deliver it.

Pure JSON-RPC bookkeeping, kept apart from the transport wiring in `arch_mcp_stdio`: a proxy inherits
the obligation it forwards — every request id it accepts from the client is answered exactly once —
and the only moment that obligation becomes visible is the moment the backend can no longer meet it.
Without it a lost connection is indistinguishable, from the client's side, from a call still running.
"""

from __future__ import annotations

from mcp.types import (
    CONNECTION_CLOSED,
    ErrorData,
    JSONRPCError,
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCResponse,
    RequestId,
)


class OutstandingReplies:
    """The client's request ids this bridge has forwarded and not yet seen answered."""

    def __init__(self) -> None:
        self._methods: dict[RequestId, str] = {}

    def accept(self, message: JSONRPCMessage) -> None:
        """Take responsibility for a request being forwarded. Notifications expect no reply."""
        match message.root:
            case JSONRPCRequest(id=request_id, method=method):
                self._methods[request_id] = method

    def settle(self, message: JSONRPCMessage) -> None:
        """Release a request the backend has answered, whether with a result or with an error."""
        match message.root:
            case JSONRPCResponse(id=request_id) | JSONRPCError(id=request_id):
                self._methods.pop(request_id, None)

    def as_connection_closed(self, reason: str) -> tuple[JSONRPCMessage, ...]:
        """One error response per unanswered id, each naming why no reply is coming.

        `CONNECTION_CLOSED` is the SDK's own code for a transport that ended mid-session, so a client
        classifies these the same way it classifies a server it lost — which is what happened.
        """
        return tuple(
            JSONRPCMessage(
                JSONRPCError(
                    jsonrpc="2.0",
                    id=request_id,
                    error=ErrorData(
                        code=CONNECTION_CLOSED,
                        message=f"{method} went unanswered: {reason}",
                    ),
                )
            )
            for request_id, method in self._methods.items()
        )


def failure_reason(failure: BaseException) -> str:
    """A single line naming what failed, flattening the groups a task group raises.

    The reason is the whole point of reporting a failure at all: "ConnectError: All connection attempts
    failed" tells an operator the backend went away, while an unnamed `ExceptionGroup` tells them only
    that something did.
    """
    match failure:
        case BaseExceptionGroup():
            return "; ".join(failure_reason(inner) for inner in failure.exceptions)
        case _:
            described = str(failure).strip()
            return f"{type(failure).__name__}: {described}" if described else type(failure).__name__
