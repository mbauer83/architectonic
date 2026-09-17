"""The in-flight journal on disk: `.arch/update/journal.json`, its lock, and the history it retires to.

One update at a time per checkout — the lock is a file created exclusively and holding the owner's
pid, so a lock left by a process that died is taken over rather than obeyed, and a lock held by the
process itself (the pid survives `os.execv`) is re-entered by the resumed new version.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from src.application.software_update.journal import JournalInvalid, UpdateJournal
from src.domain.clock import utc_now_compact
from src.infrastructure.atomic_file import write_atomic
from src.infrastructure.backend.backend_state import process_exists

UPDATE_STATE_DIR = Path(".arch") / "update"


class UpdateInProgress(RuntimeError):
    """Another `arch-update` holds this checkout's lock."""


class FileJournalStore:
    def __init__(self, root: Path) -> None:
        self.directory = root / UPDATE_STATE_DIR
        self.journal_path = self.directory / "journal.json"
        self.lock_path = self.directory / "lock"
        self.history = self.directory / "history"

    # ── Lock ──────────────────────────────────────────────────────────────────

    def acquire(self) -> None:
        """Take the lock, or raise `UpdateInProgress` naming the live holder."""
        self.directory.mkdir(parents=True, exist_ok=True)
        holder = self.lock_holder()
        if holder == os.getpid():
            return
        if holder is not None and process_exists(holder):
            raise UpdateInProgress(f"arch-update (pid {holder}) is already running in this checkout")
        if holder is not None:
            self.lock_path.unlink(missing_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))

    def release(self) -> None:
        if self.lock_holder() == os.getpid():
            self.lock_path.unlink(missing_ok=True)

    def lock_holder(self) -> int | None:
        try:
            return int(self.lock_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    # ── JournalStore port ─────────────────────────────────────────────────────

    def read(self) -> UpdateJournal | None:
        if not self.journal_path.exists():
            return None
        try:
            return UpdateJournal.from_mapping(json.loads(self.journal_path.read_text(encoding="utf-8")))
        except ValueError as exc:
            raise JournalInvalid(f"{self.journal_path}: {exc}") from exc

    def write(self, journal: UpdateJournal) -> None:
        write_atomic(self.journal_path, json.dumps(journal.to_mapping(), indent=2))

    def archive(self, journal: UpdateJournal, outcome: str) -> None:
        target = self.history / f"{utc_now_compact()}-{journal.target.version}-{outcome}.json"
        write_atomic(target, json.dumps({**journal.to_mapping(), "outcome": outcome}, indent=2))
        self.journal_path.unlink(missing_ok=True)

    def last_archived(self) -> dict[str, object] | None:
        entries = sorted(self.history.glob("*.json")) if self.history.exists() else []
        if not entries:
            return None
        return dict(json.loads(entries[-1].read_text(encoding="utf-8")))
