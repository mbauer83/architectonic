"""Activating and deactivating the confidential store, as functions any caller can run.

`try_auto_unlock` (in `store_factory`) is what a *starting* process does with the activation gate;
this module is the other half — what the ceremony that sets or clears the gate does, and how it tells
the workspace's running backend. It was the body of two CLI handlers, which meant the updater, which
has to re-authorize the store after it restarts the backend, could only have done so by shelling out to
`arch-assurance unlock` or by copying it.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.infrastructure.assurance import _credential_accounts as accounts

logger = logging.getLogger(__name__)

#: Long enough for a local backend to take the reload, short enough that an absent one does not stall
#: the ceremony. The notification is best-effort: with no backend running, the activation policy is
#: what decides at the next start.
_RELOAD_TIMEOUT_S = 3.0


@dataclass(frozen=True)
class StoreActivation:
    """What `activate_store` established: the store opened with the key on record, and its statistics."""

    db_path: Path
    stats: dict[str, Any]


def notify_backend_reload(*, authorize: bool | None = None) -> None:
    """Best-effort POST to *this workspace's* backend to reload the assurance bundle.

    ``authorize`` carries the operator's intent to the running process: True where the command grants
    access, False where it revokes it, None to leave authorization untouched. Under the manual
    activation policy this is what makes the ceremony take effect on the process that is already
    running rather than only on the next start.

    Which process that is has to be decided by what it serves. Composed from the configured port,
    this call once authorized a neighbouring workspace's backend to open *its* confidential store.
    """
    try:
        from src.infrastructure.cli._workspace_backend import workspace_backend_url  # noqa: PLC0415

        base_url = workspace_backend_url()
        if base_url is None:
            return
        payload = json.dumps({} if authorize is None else {"authorize": authorize}).encode()
        request = urllib.request.Request(
            f"{base_url}/api/assurance/reload",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=_RELOAD_TIMEOUT_S):  # noqa: S310 — loopback URL
            pass
    except Exception:  # noqa: BLE001 — no backend running: the policy applies at its next start
        logger.debug("No running backend took the assurance reload", exc_info=True)


def activate_store(db_path: Path) -> StoreActivation:
    """Verify the key opens the store, record the activation, and authorize the running backend.

    Raises ``RuntimeError`` when the store cannot be opened — the key is missing or wrong — with
    nothing recorded, so a failed ceremony never leaves a gate that says it succeeded.
    """
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore  # noqa: PLC0415

    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    try:
        stats = store.stats()
    finally:
        store.lock()
    # Record that this store was ceremonially activated at least once. Whether a future process may
    # open it unattended is a separate, deployment-level question the activation policy answers.
    accounts.write(accounts.SETUP_GATE, db_path, "1")
    # Authorize the running backend (if any) immediately: under the manual policy a plain reload
    # would re-apply the policy and stay locked, so the ceremony would do nothing.
    notify_backend_reload(authorize=True)
    return StoreActivation(db_path=db_path, stats=dict(stats))


def deactivate_store(db_path: Path) -> None:
    """Revoke access: clear the activation gate and close the store in the running backend.

    Takes effect on the running process rather than at its next start, or the caller would report
    success while access stayed open. The encryption key stays in the credential backend, so this
    bounds application-level access, not key extraction.
    """
    accounts.clear(accounts.SETUP_GATE, db_path)
    notify_backend_reload(authorize=False)
