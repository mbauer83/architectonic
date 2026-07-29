"""Signal-mutation capability predicate over the FULL configuration space.

Signal mutations (snapshot lifecycle, BOM/vulnerability/anchor imports, VEX)
require a real transactional boundary between the signal rows and their audit
records. That exists in exactly one configuration:

    store = sqlcipher AND signals = sqlcipher-colocated
    AND archive ∈ {standard, worm}   # local, same database
    AND unlocked

Every other combination denies mutations with a typed reason — cloud WORM
archives have no atomic boundary with the database, pocketbase/private-git
stores do not co-locate signals, and the plain-SQLite signals backend is
deprecated for metrics (no population path). Reads and metrics remain
available wherever the exposure policy allows. The ``encrypted`` alias
resolves per store backend (SQLCipher store → co-located); its explicit
settings migration is the upgrade path's job, not this predicate's.
"""

from __future__ import annotations

from dataclasses import dataclass

_TRANSACTIONAL_ARCHIVES = frozenset({"standard", "worm"})


@dataclass(frozen=True)
class SignalMutationAllowed:
    pass


@dataclass(frozen=True)
class SignalMutationDenied:
    reason_code: str
    message: str


SignalMutationCapability = SignalMutationAllowed | SignalMutationDenied


def _resolved_signals_backend(store_backend: str, signals_backend: str) -> str:
    if signals_backend == "encrypted":
        return "sqlcipher-colocated" if store_backend == "sqlcipher" else "sqlite"
    return signals_backend


def signal_mutation_capability(
    *,
    store_backend: str,
    signals_backend: str,
    archive_backend: str,
    unlocked: bool,
) -> SignalMutationCapability:
    resolved_signals = _resolved_signals_backend(store_backend, signals_backend)
    if store_backend != "sqlcipher":
        return SignalMutationDenied(
            reason_code="store_backend_not_transactional",
            message=(
                f"store_backend {store_backend!r} cannot commit signal rows and their "
                "audit records in one transaction; signal mutations require the "
                "sqlcipher store with co-located signals."
            ),
        )
    if resolved_signals == "sqlite":
        return SignalMutationDenied(
            reason_code="signals_backend_deprecated_sqlite",
            message=(
                "signals_backend 'sqlite' is deprecated for metrics and has no "
                "mutation path; select 'sqlcipher-colocated'."
            ),
        )
    if resolved_signals != "sqlcipher-colocated":
        return SignalMutationDenied(
            reason_code="signals_backend_not_colocated",
            message=(
                f"signals_backend {resolved_signals!r} does not share the store's "
                "transaction boundary; signal mutations require 'sqlcipher-colocated'."
            ),
        )
    if archive_backend not in _TRANSACTIONAL_ARCHIVES:
        return SignalMutationDenied(
            reason_code="archive_has_no_atomic_boundary",
            message=(
                f"archive_backend {archive_backend!r} is independent of the database — "
                "no atomic mutation+audit boundary exists. The transactional ledger "
                "with a cloud delivery outbox is the documented future path."
            ),
        )
    if not unlocked:
        return SignalMutationDenied(
            reason_code="store_locked",
            message="The confidential assurance store is locked; unlock it to mutate signals.",
        )
    return SignalMutationAllowed()
