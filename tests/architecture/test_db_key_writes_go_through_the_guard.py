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

#: Functions permitted to call the generic credential writer: the account module's own `write`, which
#: is the writer, and the guard's two named paths.
_PERMITTED_WRITERS = frozenset({"write", "store_db_key_for_rekey", "store_db_key_for_new_store"})


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


#: The modules whose `write` is a *credential* write. `write` is also how a file is written, so the
#: receiver has to be part of the match — matching the bare name flagged CSV exports and PUML renders.
_CREDENTIAL_MODULES = frozenset({"accounts", "_credential_accounts", "creds", "_credential_store"})


def _is_credential_write(node: ast.AST, *, in_accounts_module: bool) -> bool:
    if not isinstance(node, ast.Call):
        return False
    callee = node.func
    if isinstance(callee, ast.Attribute):
        receiver = callee.value
        module = receiver.id if isinstance(receiver, ast.Name) else ""
        return callee.attr in {"write", "set_credential"} and module in _CREDENTIAL_MODULES
    name = getattr(callee, "id", "")
    # Unqualified inside the account module itself, where `write` *is* the credential writer.
    return name == "set_credential" or (in_accounts_module and name == "write")


def _write_calls(tree: ast.AST, *, in_accounts_module: bool = False) -> list[tuple[str, ast.Call]]:
    """Every credential write in this module, paired with the function it sits in."""
    found: list[tuple[str, ast.Call]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if _is_credential_write(inner, in_accounts_module=in_accounts_module):
                assert isinstance(inner, ast.Call)
                found.append((node.name, inner))
    return found


def test_the_matcher_fires_on_the_call_that_destroyed_the_store() -> None:
    """Guards the guard, against the exact source that cost a store.

    A fitness function that passes because it matches nothing is the failure mode of the four repairs
    before this one. So the pattern is fed in directly: the migration write as it was written, which
    the previous matcher missed because the account was a variable.
    """
    offending = ast.parse(
        "def read(base, store_path):\n"
        "    inherited = creds.get(base)\n"
        "    if inherited is not None:\n"
        "        write(base, store_path, inherited)\n"
        "    return inherited\n"
    )
    calls = _write_calls(offending, in_accounts_module=True)
    assert [enclosing for enclosing, _ in calls] == ["read"], (
        "the matcher no longer sees the write that destroyed the store"
    )

    innocent = ast.parse("def render(path, puml):\n    path.write(puml)\n")
    assert _write_calls(innocent, in_accounts_module=True) == [], (
        "the matcher counts an ordinary file write as a credential write"
    )


def test_no_credential_write_names_its_account_dynamically() -> None:
    """The blind spot that let the sixth incident through.

    The previous version of this fitness function matched on the *argument* — a write was an offence
    only if it literally named ``DB_KEY``. The write that destroyed the store on 2026-07-31 passed the
    account as a **variable**: ``accounts.read`` fell back to a legacy account and copied whatever it
    found into the scoped one, so the call read ``write(base, store_path, inherited)`` and matched
    nothing. A write whose account is decided at run time cannot be shown not to be the db key, so it
    is forbidden outright and the guard's monopoly becomes checkable rather than merely intended.
    """
    offenders: dict[str, list[int]] = {}
    for path in _python_sources():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - not our source then
            continue
        lines = [
            call.lineno
            for enclosing, call in _write_calls(tree)
            if enclosing not in _PERMITTED_WRITERS
            and call.args
            and not (isinstance(call.args[0], ast.Attribute) and call.args[0].attr.isupper())
            and not (isinstance(call.args[0], ast.Name) and call.args[0].id.isupper())
        ]
        if lines:
            offenders[str(path.relative_to(_REPO_ROOT))] = lines

    assert offenders == {}, (
        "these write a credential to an account named at run time, so no check can tell whether it is "
        "a store's encryption key. Name the account constant:\n"
        + "\n".join(f"  {where}: lines {lines}" for where, lines in sorted(offenders.items()))
    )


def test_reading_a_credential_cannot_write_one() -> None:
    """The mechanism of the sixth incident, stated as a property.

    ``accounts.read`` migrated a legacy credential onto the scoped account, so a *read* wrote — and
    because a failed read was indistinguishable from an absent one, a keychain timeout was enough to
    trigger it. Nothing that reads may write: a lookup has no business changing what it looked at.
    """
    tree = ast.parse(_ACCOUNTS.read_text(encoding="utf-8"))
    writers_by_function = {enclosing for enclosing, _ in _write_calls(tree, in_accounts_module=True)}
    assert writers_by_function <= {"write"}, (
        f"these functions in _credential_accounts write a credential: {sorted(writers_by_function)}. "
        "Only `write` may; a read that writes is how the live store's key was replaced by a stale one."
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
