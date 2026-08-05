"""Working out what state the assurance store is in, for `arch-assurance status`.

Whether the store is open is a fact about a process, not about the files on disk. The key in the
keychain and the activation gate together say the store *may* be opened; whether it *is* open
depends on the deployment's activation policy and on which process is asking.

A CLI invocation is its own short-lived process, so asking whether *it* could open the store
answers a question nobody has. What an operator wants to know is whether the backend serving the
capability is holding it open — so that is what this reports, falling back to what a newly started
process would do when no backend answers.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

#: Long enough for a local backend to answer, short enough that a missing one does not stall the
#: command. A backend that cannot answer in this window is reported as absent, never as open.
_BACKEND_PROBE_TIMEOUT_S = 2.0


def backend_holds_store_open() -> bool | None:
    """Whether *this workspace's* backend has the store open, or None when none answers.

    The backend is located by what it serves, not by the configured port: the port may belong to
    another workspace's backend, whose store is a different store and none of this one's business.
    """
    try:
        from src.infrastructure.cli._workspace_backend import workspace_backend_url  # noqa: PLC0415

        base_url = workspace_backend_url()
        if base_url is None:
            return None
        request = urllib.request.Request(
            f"{base_url}/api/assurance/status",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=_BACKEND_PROBE_TIMEOUT_S) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    return bool(payload.get("unlocked"))


def _a_new_process_would_open_it(db_path: Path) -> bool:
    """Run the same startup unlock a new process runs, against a throwaway store.

    This is what predicts the next process's behaviour, and it is the activation policy that
    decides: under 'persistent' an activated store opens, under 'manual' it does not.
    """
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore  # noqa: PLC0415
    from src.infrastructure.assurance.store_factory import try_auto_unlock  # noqa: PLC0415

    probe = SQLCipherAssuranceStore(db_path)
    try_auto_unlock(probe, "sqlcipher", db_path)
    opened = probe.is_unlocked()
    probe.lock()
    return opened


def _sqlcipher_state(db_path: Path, *, setup_confirmed: bool) -> tuple[bool, str, str]:
    live = backend_holds_store_open()
    if live is True:
        return True, "unlocked", "The running backend is holding the store open."
    if not setup_confirmed:
        return False, "locked_needs_activation", (
            "This store has never been activated. Run `arch-assurance unlock`."
        )
    if live is False:
        return False, "locked", (
            "Activated, but the running backend is not holding the store open. Run "
            "`arch-assurance unlock` to authorize it."
        )
    if _a_new_process_would_open_it(db_path):
        return True, "unlocked", (
            "Activated, and a newly started process opens the store by itself under this "
            "activation policy. No backend is running to confirm it."
        )
    return False, "locked", (
        "Activated, but no process is holding the store open, and a newly started one would not "
        "open it by itself under this activation policy. Run `arch-assurance unlock` on the "
        "process that needs it."
    )


def resolve_lock_state(
    *,
    store_backend: str,
    db_path: Path,
    key_present: bool,
    setup_confirmed: bool,
    workspace_root: Path,
) -> tuple[bool, str, str]:
    """Return (unlocked, status, note) for the configured backend."""
    if store_backend == "sqlcipher" and db_path.exists() and key_present:
        return _sqlcipher_state(db_path, setup_confirmed=setup_confirmed)
    if store_backend == "private-git" and not (workspace_root / ".arch-assurance-git").exists():
        return False, "not_initialised", "No private-git assurance repository exists yet."
    if not key_present:
        return False, "not_initialised", (
            "No encryption key is in the credential store. Run `arch-assurance init`."
        )
    return False, "locked", "The store is not open in this process."
