"""Which credential account holds which secret, and for which store.

A secret is scoped to the store it opens. That was not always so: the account names were bare
constants — `db-encryption-key`, `db-recovery-key` — copied into seven modules, and every store on
the machine shared them. Initialising *any* store therefore overwrote the key of whichever store
held that account, including a live one, and `init_store` writes the recovery key in the same call,
so the recovery key was destroyed alongside the thing it exists to recover. A temporary store under
a temp directory was enough to do it, permanently, with no error.

Scoping the account to the store's resolved path removes the collision at its root: two stores
cannot contend for one account, so initialising one cannot reach another. The path is hashed rather
than embedded — it is not a secret, but a credential account name is visible in OS credential UIs
and there is no reason to publish a filesystem layout there.

**Reading falls back to the unscoped account**, so a store initialised before this scoping keeps
opening with no migration step and no operator action. Writing never does: a write must land on the
scoped account, or the collision is back. For the same reason nothing here deletes an unscoped
account as a side effect of a write — a store at some other path doing so is precisely the bug.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.infrastructure.assurance import _credential_store as creds

#: The secret that decrypts a SQLCipher store.
DB_KEY = "db-encryption-key"

#: The second, independently-generated key kept so access survives losing the first.
RECOVERY_KEY = "db-recovery-key"

#: The secret that decrypts a Fernet-encrypted private-git store.
GIT_KEY = "private-git-encryption-key"

#: That store's recovery counterpart.
GIT_RECOVERY_KEY = "private-git-recovery-key"

#: The activation gate: set by `unlock`, cleared by `lock`. Not a secret — its presence is the
#: fact — but scoped for the same reason, so unlocking one store cannot activate another.
SETUP_GATE = "setup-confirmed"


def scoped_account(base: str, store_path: Path) -> str:
    """`base`, qualified by the store it belongs to."""
    digest = hashlib.sha256(str(store_path.resolve()).encode()).hexdigest()[:12]
    return f"{base}.{digest}"


def read(base: str, store_path: Path) -> str | None:
    """This store's secret: the scoped account, or the unscoped one it may predate.

    **A read never writes.** It used to: a secret found only at the unscoped account was copied to the
    scoped one, so a pre-scoping store migrated itself on first use. That copy destroyed the live store
    on 2026-07-31, and the mechanism is worth stating exactly, because it defeated five rounds of
    guards that were all built on the test side.

    ``creds.get`` returned ``None`` for a *failed* read as well as an absent one — on WSL2 it spawns
    ``powershell.exe``, and under load that spawn can time out. So a transient failure to read the
    scoped account was indistinguishable from the account not existing; the fallback then found a
    stale unscoped key from a store two initialisations ago and wrote it over the live one. A read, in
    a process no test guard covers, silently replaced the key with one that opened nothing.

    ``creds.get`` now raises rather than flattening failure into absence, which removes the
    misdiagnosis. Removing the write removes the consequence: with both gone there is no path from
    reading a credential to losing one. The cost is that a pre-scoping store consults two accounts on
    every read instead of migrating once — two ``powershell.exe`` spawns where there was one, for a
    store nobody has any more. That is the right way round: the saving was never worth a destructive
    write on the read path.
    """
    scoped = creds.get(scoped_account(base, store_path))
    if scoped is not None:
        return scoped
    return creds.get(base)


def write(base: str, store_path: Path, value: str) -> None:
    """Store this store's secret under its scoped account, and only there."""
    creds.set_credential(scoped_account(base, store_path), value)


def clear(base: str, store_path: Path) -> None:
    """Remove this store's secret, scoped and unscoped alike.

    Both, because revocation must actually revoke: leaving an unscoped account behind would let the
    next read fall back to it and re-open a store the operator just locked. This is the one
    operation that may touch the unscoped account, and it is safe to because the caller is asking
    for exactly this store's access to end.
    """
    creds.delete(scoped_account(base, store_path))
    creds.delete(base)


def present(base: str, store_path: Path) -> bool:
    """Whether this store has the named secret at all — for readiness probes."""
    return read(base, store_path) is not None
