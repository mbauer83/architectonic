"""Test stores derive their key with one PBKDF2 iteration; the product's stores keep the library default.

`tests/support/store_key_derivation.py`, applied by `tests/conftest.py`, lowers SQLCipher's
process-wide default so a store connection costs ~0.2 ms rather than 0.1 s — summed over the tests
that use a store, 172 s became 77 s. That is sound only while the product never states an iteration
count itself: then the library default governs every real store, and the suite's setting governs
exactly the stores it makes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.support.store_key_derivation import TEST_STORE_KDF_ITERATIONS

_SRC = Path(__file__).resolve().parents[2] / "src"


def test_the_suite_runs_with_the_cheap_default() -> None:
    sqlcipher3 = pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
    conn = sqlcipher3.connect(":memory:")
    try:
        (value,) = conn.execute("PRAGMA cipher_default_kdf_iter").fetchone()
    finally:
        conn.close()

    assert int(value) == TEST_STORE_KDF_ITERATIONS


def test_the_product_never_states_an_iteration_count() -> None:
    statement = re.compile(r"kdf_iter|cipher_compatibility|cipher_default_", re.IGNORECASE)
    stating = sorted(
        path.relative_to(_SRC.parent).as_posix()
        for path in _SRC.rglob("*.py")
        if statement.search(path.read_text(encoding="utf-8"))
    )

    assert not stating, f"{stating} set a key-derivation parameter; the suite's default would then not match"
