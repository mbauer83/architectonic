"""A test store's key costs one hash, not 256,000.

SQLCipher derives a page key from the passphrase with PBKDF2 on the first access of *every*
connection: 0.1 s each, and a store opens one connection per thread, so an HTTP test pays it again per
server thread. `cipher_default_kdf_iter` is SQLCipher's process-wide default, so lowering it before any
store exists governs every store a test process creates or opens — the template and every copy alike —
while the product, which never sets it, keeps the library default. The same trade a suite makes when it
swaps in a fast password hasher: the keys are throwaway, and what is under test is the store, not PBKDF2.

Its one consequence: a store made at the default count does not open in a process with this setting,
nor the reverse. A store shared with a subprocess must be made and opened under the same default.
`tests/architecture/test_test_stores_derive_their_key_once.py` holds that the product never states a
count, which is what keeps the suite's stores and the product's governed by different defaults.
"""

from __future__ import annotations

#: PBKDF2 iterations for every store a test process makes or opens.
TEST_STORE_KDF_ITERATIONS = 1


def cheapen_test_store_key_derivation() -> None:
    """Set SQLCipher's process-wide default iteration count; a no-op without sqlcipher3."""
    try:
        import sqlcipher3  # type: ignore[import-untyped]
    except ImportError:
        return
    conn = sqlcipher3.connect(":memory:")
    try:
        conn.execute(f"PRAGMA cipher_default_kdf_iter = {TEST_STORE_KDF_ITERATIONS}")
    finally:
        conn.close()
