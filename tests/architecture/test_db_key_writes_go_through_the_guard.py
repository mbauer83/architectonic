"""No code writes a store's encryption key except through the guard.

This is the test four earlier repairs did not have, and its absence is why there were four of them.
Each incident produced a guard on the entrance that incident had used — an in-memory credential
backend, an in-process forbid flag, a credentials-directory redirect — and each held until something
came in through a different door. The fifth came through production code (`rotate_key`), where no
test-side guard reaches.

A key and the file it opens are one fact stored in two places, and a write that breaks their
correspondence cannot be undone: the ciphertext survives and the plaintext is gone for ever. So the
requirement is structural rather than case-by-case — there is exactly one function that may replace
this credential, it verifies before it writes, and this fitness function is what stops a sixth writer
appearing beside it.

Deliberately an AST walk over the source rather than a runtime check: the point is that no such call
*exists*, which a runtime guard cannot say, because the call it fails to intercept is the one nobody
knew to look for.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The guard itself, which is where the one permitted write lives.
_GUARD = _REPO_ROOT / "src" / "infrastructure" / "assurance" / "_db_key_guard.py"

#: Declares the accounts, and holds the generic `write` the guard calls. It may name `DB_KEY`
#: because defining a constant is not writing to it.
_ACCOUNTS = _REPO_ROOT / "src" / "infrastructure" / "assurance" / "_credential_accounts.py"

_EXEMPT = frozenset({_GUARD, _ACCOUNTS})


def _is_db_key_write(node: ast.AST) -> bool:
    """A call that writes the db-encryption-key account: ``…write(…DB_KEY, …)``.

    Matched on the argument rather than the callee, because the callee is spelled several ways
    (`accounts.write`, `write`, an alias) and the argument is the part that identifies the secret.
    """
    if not isinstance(node, ast.Call):
        return False
    callee = node.func
    name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", "")
    if name not in {"write", "set_credential"}:
        return False
    for argument in node.args:
        if isinstance(argument, ast.Attribute) and argument.attr == "DB_KEY":
            return True
        if isinstance(argument, ast.Name) and argument.id == "DB_KEY":
            return True
    return False


def _python_sources() -> list[Path]:
    return [
        path
        for directory in ("src", "tools", "mcp")
        for path in (_REPO_ROOT / directory).rglob("*.py")
        if "__pycache__" not in path.parts
    ]


def test_only_the_guard_writes_a_stores_encryption_key() -> None:
    offenders: dict[str, list[int]] = {}
    for path in _python_sources():
        if path.resolve() in _EXEMPT:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - not our source then
            continue
        lines = [node.lineno for node in ast.walk(tree) if _is_db_key_write(node)]
        if lines:
            offenders[str(path.relative_to(_REPO_ROOT))] = lines

    assert offenders == {}, (
        "these write a store's encryption key without going through `_db_key_guard`, which is how "
        "the store has been made permanently unopenable five times:\n"
        + "\n".join(f"  {where}: lines {lines}" for where, lines in sorted(offenders.items()))
    )


def test_the_guard_offers_exactly_two_ways_to_write_the_key() -> None:
    """Rekeying an existing store, or replacing the store outright. A third would be a way to write
    the credential without saying which of the two it is — which is the blind write itself."""
    import src.infrastructure.assurance._db_key_guard as guard

    writers = {
        name
        for name in vars(guard)
        if name.startswith("store_db_key")
    }
    assert writers == {"store_db_key_for_rekey", "store_db_key_for_new_store"}


def test_the_lifecycle_module_uses_both_and_nothing_else() -> None:
    """States which path is which, so a future edit that swaps them fails here rather than in a
    keychain: creation cannot verify (there is no file yet), rekeying must."""
    source = (_REPO_ROOT / "src" / "infrastructure" / "assurance" / "lifecycle.py").read_text()
    assert "store_db_key_for_new_store(db_path, key)" in source, "init_store must name the creation path"
    assert "store_db_key_for_rekey(db_path, new_key)" in source, "rotate_key must name the verified path"
