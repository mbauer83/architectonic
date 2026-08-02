"""Reset the REST layer's process state between tests.

`state.py` holds five module globals that `arch_backend.main()` and every router test set through
`init_state`. Two of them are `_admin_mode` and `_read_only`: a test that initialises with
`admin_mode=True` leaves the *whole process* in admin mode, so a later test asserting that an
enterprise write is refused gets a 200 and passes for the wrong reason. That is a false green of the
kind this release has been about removing, and it needs no flake to be worth closing.

Here rather than in `state.py` because it is test-only, and because adding it there put that module
18 counted lines over the 350 hard limit — a baseline entry the handoff explicitly forbids adding.
The cost of living outside the module is a second list of global names, so
`test_rest_state_reset_covers_every_global` holds the two equal: a global added to `state.py`
without being reset here fails that test rather than leaking silently.
"""

from __future__ import annotations

from src.infrastructure.rest.routers import state

#: Every module global `init_state` writes, and the value it starts life with.
INITIAL_STATE: dict[str, object] = {
    "_repo": None,
    "_repo_root": None,
    "_enterprise_root": None,
    "_admin_mode": False,
    "_read_only": False,
}


def reset_state_for_test() -> None:
    """Return the module to its unconfigured state, under its own lock."""
    with state._state_lock:  # noqa: SLF001 - resetting this module's state is the point
        for name, value in INITIAL_STATE.items():
            setattr(state, name, value)
