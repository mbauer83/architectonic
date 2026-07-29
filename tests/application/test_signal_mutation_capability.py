"""§6.0(a) capability predicate over the REAL factory cross-product: exactly
one configuration allows signal mutations; every other combination denies with
a typed reason; the 'encrypted' alias resolves per store backend."""

from __future__ import annotations

import itertools

import pytest

from src.application.security_signals.capability import (
    SignalMutationAllowed,
    SignalMutationDenied,
    signal_mutation_capability,
)

STORES = ("sqlcipher", "pocketbase", "private-git")
SIGNALS = ("sqlcipher-colocated", "sqlite", "encrypted")
ARCHIVES = ("standard", "worm", "s3-worm", "azure-blob-worm")
LOCK = (True, False)


def _allowed(store: str, signals: str, archive: str, unlocked: bool) -> bool:
    resolved = ("sqlcipher-colocated" if store == "sqlcipher" else "sqlite") \
        if signals == "encrypted" else signals
    return (
        store == "sqlcipher"
        and resolved == "sqlcipher-colocated"
        and archive in ("standard", "worm")
        and unlocked
    )


@pytest.mark.parametrize(
    ("store", "signals", "archive", "unlocked"),
    list(itertools.product(STORES, SIGNALS, ARCHIVES, LOCK)),
)
def test_full_cross_product(store: str, signals: str, archive: str, unlocked: bool) -> None:
    result = signal_mutation_capability(
        store_backend=store, signals_backend=signals,
        archive_backend=archive, unlocked=unlocked,
    )
    if _allowed(store, signals, archive, unlocked):
        assert isinstance(result, SignalMutationAllowed)
    else:
        assert isinstance(result, SignalMutationDenied)
        assert result.reason_code
        assert result.message


class TestReasons:
    def test_cloud_worm_denies_with_the_atomic_boundary_reason(self) -> None:
        result = signal_mutation_capability(
            store_backend="sqlcipher", signals_backend="sqlcipher-colocated",
            archive_backend="s3-worm", unlocked=True,
        )
        assert isinstance(result, SignalMutationDenied)
        assert result.reason_code == "archive_has_no_atomic_boundary"

    def test_public_sqlite_is_deprecated_not_merely_denied(self) -> None:
        result = signal_mutation_capability(
            store_backend="sqlcipher", signals_backend="sqlite",
            archive_backend="standard", unlocked=True,
        )
        assert isinstance(result, SignalMutationDenied)
        assert result.reason_code == "signals_backend_deprecated_sqlite"

    def test_encrypted_alias_resolves_per_store_backend(self) -> None:
        colocated = signal_mutation_capability(
            store_backend="sqlcipher", signals_backend="encrypted",
            archive_backend="standard", unlocked=True,
        )
        assert isinstance(colocated, SignalMutationAllowed)
        plaintext = signal_mutation_capability(
            store_backend="pocketbase", signals_backend="encrypted",
            archive_backend="standard", unlocked=True,
        )
        assert isinstance(plaintext, SignalMutationDenied)

    def test_locked_store_is_its_own_reason(self) -> None:
        result = signal_mutation_capability(
            store_backend="sqlcipher", signals_backend="sqlcipher-colocated",
            archive_backend="worm", unlocked=False,
        )
        assert isinstance(result, SignalMutationDenied)
        assert result.reason_code == "store_locked"
