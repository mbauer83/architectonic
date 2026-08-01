"""Build a test application configured the way the real one is.

A router mounted on a bare ``FastAPI()`` behaves differently from the same router in the product:
no typed error envelope, no request id, and no declared ``Cache-Control``. Tests written against
that bare app assert a shape no client ever receives — which is how a confidentiality header can be
verified by a green suite and absent in production.

So the cross-cutting pieces are assembled here, once, and every router test that cares about
responses rather than handler internals uses this instead of composing its own app.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from src.infrastructure.backend.cache_directive import apply_cache_directive
from src.infrastructure.backend.read_model_caching import conditional_read_middleware
from src.infrastructure.rest.contracts.error_responses import install_error_contracts


def build_api_app(*routers: APIRouter) -> FastAPI:
    """A FastAPI app carrying the same response contracts the product's app carries.

    Registration order is the product's, because middleware order is behaviour: the conditional-read
    middleware sits *inside* the cache directive so a 304 keeps the ``no-cache`` it chose while every
    other response gets its operation's declared directive, and the error contracts are outermost so
    a failure anywhere inside still produces an envelope.
    """
    app = FastAPI(redirect_slashes=False)
    app.middleware("http")(conditional_read_middleware)
    app.middleware("http")(apply_cache_directive)
    # Registered last so its middleware is outermost, as in the real application.
    install_error_contracts(app)
    for router in routers:
        app.include_router(router)
    return app
