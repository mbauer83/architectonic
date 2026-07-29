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

    A secret found only at the unscoped account is **copied to the scoped one**, so a store written
    before scoping migrates itself on first use and needs no operator step. The copy cannot cause a
    collision: it writes the scoped account and never touches the unscoped one, so a store at some
    other path is unaffected either way.

    It also keeps the fallback from costing anything twice. A credential read is a round trip to the
    OS backend — on WSL2 a `powershell.exe` spawn — and consulting two accounts on every read would
    double that for the lifetime of the deployment.
    """
    scoped = creds.get(scoped_account(base, store_path))
    if scoped is not None:
        return scoped
    inherited = creds.get(base)
    if inherited is not None:
        write(base, store_path, inherited)
    return inherited


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
