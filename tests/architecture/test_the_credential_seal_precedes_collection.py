"""No test module can reach the real credential backend, even while it is being imported.

The suite's guards against the live store's key were fixtures, and fixtures start after collection.
A module that built the module registry at import time — for a parameter list — probed the
confidential-store capability during collection, selected the real OS credential backend, read the
live store's key, and left a registry holding the assurance diagram types for its whole worker. A
developer box then registered what CI's store-less job did not.

What this module observes at its own import is what every test module observes at its import.
"""

from __future__ import annotations

import os

from src.infrastructure.assurance import _credential_store
from src.infrastructure.assurance._credential_store import (
    _CREDENTIALS_DIR_ENV,
    _FORBID_REAL_BACKEND_ENV,
)

_FORBIDDEN_AT_IMPORT = os.environ.get(_FORBID_REAL_BACKEND_ENV)
_CREDENTIALS_DIR_AT_IMPORT = os.environ.get(_CREDENTIALS_DIR_ENV)
_BACKEND_AT_IMPORT = type(_credential_store._backend).__name__  # noqa: SLF001


def test_real_backend_selection_is_forbidden_before_collection() -> None:
    assert _FORBIDDEN_AT_IMPORT, "a test module was imported while a real backend could be selected"


def test_credentials_are_redirected_before_collection() -> None:
    assert _CREDENTIALS_DIR_AT_IMPORT, "a test module was imported before credentials were redirected"


def test_the_backend_a_module_sees_at_import_is_in_memory() -> None:
    assert _BACKEND_AT_IMPORT == "_InMemoryCredentialBackend", _BACKEND_AT_IMPORT


def test_the_deployment_store_is_absent_to_the_suite() -> None:
    """CI's pytest job has no store; the suite behaves as if no machine had one."""
    from src.infrastructure.app_bootstrap import get_module_registry

    assert get_module_registry().find_diagram_type("bowtie") is None
