"""A request made by the operator of this machine, through this project's own command line.

Some operations change what the running process may do rather than what the repository holds:
authorizing it to open the confidential store is one. No principal exists yet to ask, so such an
operation is accepted only when two things say an operator on this machine sent it:

* **the client is on the loopback**, so nothing elsewhere on the network can reach it, a reverse
  proxy included (a proxied request arrives from the proxy's address);
* **it carries `OPERATOR_REQUEST_HEADER`**, which a browser will not attach to a cross-origin
  request without a preflight this backend does not grant, so a web page in the operator's browser
  cannot send it either.

The command line sets the header; nothing in the GUI does.
"""

from __future__ import annotations

from starlette.requests import Request

from src.infrastructure.backend.bind_policy import is_loopback

#: The header this project's command line sends with an operator request.
OPERATOR_REQUEST_HEADER = "X-Arch-Operator-Request"
OPERATOR_REQUEST_VALUE = "1"


def operator_request_headers() -> dict[str, str]:
    """The headers a client attaches to make its request an operator request."""
    return {OPERATOR_REQUEST_HEADER: OPERATOR_REQUEST_VALUE}


def is_local_operator_request(request: Request) -> bool:
    """Whether `request` came from this machine's loopback and carries the operator header."""
    client = request.client
    return (
        client is not None
        and is_loopback(client.host)
        and request.headers.get(OPERATOR_REQUEST_HEADER) == OPERATOR_REQUEST_VALUE
    )
