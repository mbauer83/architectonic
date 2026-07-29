"""Accessors for the `storage:` settings section — assurance store, signals and archive
backends, the classification ceiling, the activation policy, and the read-model seam.

Split out of `settings.py`: these carry their own validation vocabularies and change with
the assurance capability rather than with the backend or the diagram renderer. Same shape
as the `assurance.*` and `viewpoints.*` accessor modules beside it — including reading
`settings.load_settings` / `settings._DEFAULTS` through the module object rather than by
name import, so a test that monkeypatches `settings.load_settings` still takes effect here.
"""

from __future__ import annotations

from src.config import settings
from src.domain.assurance.classification import TLP_ORDER

_VALID_ACTIVATION_POLICIES = frozenset({"manual", "persistent"})
_VALID_STORE_BACKENDS = frozenset({"sqlcipher", "pocketbase", "private-git"})
_VALID_SIGNALS_BACKENDS = frozenset({"sqlcipher-colocated", "sqlite", "encrypted"})
_VALID_ARCHIVE_BACKENDS = frozenset({"standard", "worm", "s3-worm", "azure-blob-worm"})
_VALID_TLP_LEVELS = frozenset(TLP_ORDER)



def _storage_assurance_value(key: str) -> object:
    storage = settings.load_settings().get("storage", {})
    if not isinstance(storage, dict):
        return settings._DEFAULTS["storage"]["assurance"][key]  # type: ignore[index]
    assurance = storage.get("assurance", {})
    if not isinstance(assurance, dict):
        return settings._DEFAULTS["storage"]["assurance"][key]  # type: ignore[index]
    return assurance.get(key, settings._DEFAULTS["storage"]["assurance"][key])  # type: ignore[index]


def storage_assurance_store_backend() -> str:
    """Return the active assurance store backend name.

    Fails closed (raises ValueError) for unknown backends so misconfiguration
    surfaces at startup rather than at first use.
    """
    value = _storage_assurance_value("store_backend")
    candidate = str(value).strip() if isinstance(value, str) else "sqlcipher"
    if candidate not in _VALID_STORE_BACKENDS:
        raise ValueError(
            f"Unknown storage.assurance.store_backend: {candidate!r}. "
            f"Supported: {sorted(_VALID_STORE_BACKENDS)}"
        )
    return candidate


def storage_assurance_signals_backend() -> str:
    """Return the active signals backend name. Fails closed on unknown values."""
    value = _storage_assurance_value("signals_backend")
    candidate = str(value).strip() if isinstance(value, str) else "sqlcipher-colocated"
    if candidate not in _VALID_SIGNALS_BACKENDS:
        raise ValueError(
            f"Unknown storage.assurance.signals_backend: {candidate!r}. "
            f"Supported: {sorted(_VALID_SIGNALS_BACKENDS)}"
        )
    return candidate


def storage_assurance_archive_backend() -> str:
    """Return the active archive backend name. Fails closed on unknown values.

    'standard'        — append-only hash-chained log (SQLCipherAssuranceArchive).
    'worm'            — extends standard with DEK encryption, legal holds,
                        crypto-shredding, RFC 3161; requires store_backend 'sqlcipher'.
    's3-worm'         — S3 Object Lock WORM; independent of store_backend.
    'azure-blob-worm' — Azure Blob immutability-policy WORM; independent of
                        store_backend.
    """
    value = _storage_assurance_value("archive_backend")
    candidate = str(value).strip() if isinstance(value, str) else "standard"
    if candidate not in _VALID_ARCHIVE_BACKENDS:
        raise ValueError(
            f"Unknown storage.assurance.archive_backend: {candidate!r}. "
            f"Supported: {sorted(_VALID_ARCHIVE_BACKENDS)}"
        )
    return candidate


def storage_assurance_max_classification() -> str:
    """Return the TLP max-classification ceiling for MCP exposure control.

    Artifacts with a TLP level *above* this ceiling are withheld at the
    arch-assurance-read boundary. Defaults to TLP:AMBER.
    """
    value = _storage_assurance_value("max_classification")
    candidate = str(value).strip().upper() if isinstance(value, str) else "TLP:AMBER"
    if candidate not in _VALID_TLP_LEVELS:
        return "TLP:AMBER"
    return candidate


def storage_assurance_activation_policy() -> str:
    """Return whether a newly started process may authorize itself from the activation gate.

    'manual' (default) — a new process starts locked. `unlock` authorizes the process that is
                         running, for its lifetime. Suits a workstation, where a restart is
                         already a human act and walk-up access is the threat.
    'persistent'       — a new process authorizes itself from the activation gate until `lock`
                         revokes it. Suits a server, where an unattended reboot must not take
                         the capability down.

    Fails closed on an unrecognised value: a misspelt policy must not silently grant the more
    permissive behaviour. Note the bound — this governs application-level access, not key
    extraction; the key stays in the OS keychain under either policy, so anyone able to read the
    credential store is unaffected.
    """
    value = _storage_assurance_value("activation_policy")
    candidate = str(value).strip().lower() if isinstance(value, str) else "manual"
    if candidate not in _VALID_ACTIVATION_POLICIES:
        raise ValueError(
            f"Unknown storage.assurance.activation_policy: {candidate!r}. "
            f"Supported: {sorted(_VALID_ACTIVATION_POLICIES)}"
        )
    return candidate


def storage_read_model_seam() -> dict[str, object]:
    """Return the storage.read_model seam dict (reserved for future FTS-backend toggle)."""
    storage = settings.load_settings().get("storage", {})
    if not isinstance(storage, dict):
        return {}
    read_model = storage.get("read_model", {})
    return dict(read_model) if isinstance(read_model, dict) else {}
