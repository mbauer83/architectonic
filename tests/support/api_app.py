"""Build a test application configured the way the real one is.

A router mounted on a bare ``FastAPI()`` behaves differently from the same router in the product: no
typed error envelope, no request id, no declared ``Cache-Control``, and no module registry on app
state. Tests written against that bare app assert a shape no client ever receives — which is how a
confidentiality header can be verified by a green suite and absent in production, and how a handler
came to read process-wide catalogs because the injectable ones were not there to take.

So the cross-cutting pieces are assembled here, once, and every router test that cares about
responses rather than handler internals uses this instead of composing its own app.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from src.infrastructure.app_bootstrap import install_module_registry
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
    # The registry and its catalogs, on app state, exactly as the product installs them. Without this
    # a handler taking `runtime_catalogs_dependency` fails at request time, so a test app could only
    # exercise handlers that read process state instead — which is how eleven of them came to.
    # `dependency_overrides` still works: this is the value an override replaces.
    install_module_registry(app)
    app.middleware("http")(conditional_read_middleware)
    app.middleware("http")(apply_cache_directive)
    # Registered last so its middleware is outermost, as in the real application.
    install_error_contracts(app)
    for router in routers:
        app.include_router(router)
    return app
