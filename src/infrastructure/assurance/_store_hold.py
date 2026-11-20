"""Who has a store file open, and who may replace it.

`init --force` once moved a new file onto a store's path while a running backend still had the old
one open. That backend went on writing its own write-ahead log at the same path, against a file the
path no longer named, and the next open reported `database disk image is malformed`.

A store file can be swapped, rewritten or restored over only when nothing has it open, so that is
made a fact the operating system holds rather than one anybody infers:

* whatever **opens** a store keeps a *shared* hold for as long as it is open — any number of
  processes may, a backend and a command line among them;
* whatever **replaces** the file needs the hold *alone* for as long as the replacement runs, and is
  refused if it cannot have it. While it has it, nothing can open the store either, so there is no
  moment between the answer and the replacement for a reader to arrive in.

The hold is an `flock` on a file beside the store. Beside it, because that is the one place shared
by exactly the processes that can reach the store — another workspace, a container on the same
volume — which a process id recorded in one workspace's state directory is not. An `flock`, because
the kernel releases it when its holder exits however it exits: the file a killed process leaves
behind holds nothing, so there is no staleness to judge and nothing here ever removes that file.

SQLite's own locks on the database were the first candidate, since every reader already takes them.
They can only be asked through a connection that has decrypted the first page, and the store most
in need of reinitialising is the one whose key is lost; and the asking connection, if it turns out
to be alone, checkpoints the log as it closes — a lookup that repairs what it looked at.

`fcntl` is what the rest of the product's locking uses (`backend_start_lock`); the platforms the
credential store supports — Linux, WSL2, macOS — all have it.
"""

from __future__ import annotations

import fcntl
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


class StoreReplacementRefusedError(RuntimeError):
    """The store file was left alone because a process has it open, or may have."""


def hold_path(db_path: Path) -> Path:
    """The file beside a store that its holds are taken on. Its existence says nothing."""
    return db_path.with_name(db_path.name + ".hold")


def _descriptor_for(db_path: Path) -> int:
    return os.open(hold_path(db_path), os.O_RDWR | os.O_CREAT, 0o600)


class OpenStoreHold:
    """The shared hold one opener of a store keeps from opening it until closing it."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._descriptor: int | None = None

    def take(self) -> None:
        """Mark the store as open here. Refuses while a replacement of the file is running."""
        if self._descriptor is not None:
            return
        try:
            descriptor = _descriptor_for(self._db_path)
        except OSError as exc:
            self._warn_unmarked(exc)
            return
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            raise RuntimeError(
                f"The assurance store at {self._db_path} is being replaced by another process "
                "(a reinitialisation, a key rotation or a restore). Open it again once that has "
                "finished."
            ) from None
        except OSError as exc:
            os.close(descriptor)
            self._warn_unmarked(exc)
            return
        self._descriptor = descriptor

    def release(self) -> None:
        """Stop marking the store as open here. Closing the descriptor is what lets go."""
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is not None:
            os.close(descriptor)

    def _warn_unmarked(self, exc: OSError) -> None:
        # Opening goes ahead: a filesystem that cannot hold a lock must not make a store unusable.
        # A replacement on that filesystem meets the same error and refuses, so the store is still
        # not replaced under this process — it is only not replaceable at all until that is fixed.
        logger.warning(
            "Could not mark the assurance store at %s as open (%s); a replacement of the file "
            "cannot see this process",
            self._db_path,
            exc,
        )


@contextmanager
def sole_access(db_path: Path, *, to: str) -> Iterator[None]:
    """Hold the store alone for the block, or refuse *to* do what the caller was about to.

    Refuses when any process has the store open, and equally when that cannot be established: an
    answer nobody could get is not the answer "nobody". Nothing is removed on any path — the file
    the hold is taken on stays, whoever made it.
    """
    try:
        descriptor = _descriptor_for(db_path)
    except OSError as exc:
        raise _undetermined(db_path, to, exc) from exc
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise _held_open(db_path, to) from None
        except OSError as exc:
            raise _undetermined(db_path, to, exc) from exc
        yield
    finally:
        os.close(descriptor)


def _held_open(db_path: Path, to: str) -> StoreReplacementRefusedError:
    return StoreReplacementRefusedError(
        f"Refusing to {to} the assurance store at {db_path}: it is open in a running process, "
        "which would go on writing to a file that is no longer the store. Nothing was changed. "
        "Stop the backend that serves it (`arch-backend --stop`), or lock the store "
        "(`arch-assurance lock`), in every workspace that uses this store; wait for any other "
        "`arch-assurance` command on it to finish; then run this again."
    )


def _undetermined(db_path: Path, to: str, exc: OSError) -> StoreReplacementRefusedError:
    return StoreReplacementRefusedError(
        f"Refusing to {to} the assurance store at {db_path}: whether a running process has it "
        f"open cannot be established ({exc}), and it is not replaced on a guess. Nothing was "
        f"changed. The check takes a lock on {hold_path(db_path)}; make that file writable and "
        "its filesystem one that supports file locks, then run this again."
    )
