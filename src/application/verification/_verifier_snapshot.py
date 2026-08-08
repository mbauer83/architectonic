"""One byte-image of a repository, and the only place verification reads the filesystem.

Verification's cost and its consistency requirement are separable. Acquisition — a stat sweep plus
every file's bytes — is about a megabyte on a real repository and finishes in well under a second.
The minutes are rule evaluation, which is pure computation over bytes already held.

So exclusivity is held for acquisition and released before evaluation, the same shape the git-sync
publisher already uses: it computes entries and writes its transaction intent with no gate held, and
takes the gate only for the publish window. Hold exclusivity for the part that must be indivisible,
not for the part that is expensive.

**Acquisition does not take the gate itself, and must not.** Whole-repository verification runs
inside `gate.writing()` on the promote and cascade-delete paths, and the gate is not reentrant — a
verifier that acquired READ would wait on its own caller forever. Who acquires is therefore the
caller's decision, made where the gate context is known: a read path wraps this in `gate.reading()`,
a write path calls it holding WRITE, which is strictly stronger.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.application.verification._verifier_inventory import FileInventory


@dataclass(frozen=True)
class RepositorySnapshot:
    """The files a pass will verify, and their contents as of one moment."""

    inventory: FileInventory
    contents: dict[Path, str]

    def read(self, path: Path) -> str | None:
        """The bytes this snapshot holds for *path*, or None if it holds none.

        None means "not in this snapshot" — a document outside the inventory, or a file added after
        acquisition — and the caller falls back to the filesystem. It never means "empty file".
        """
        return self.contents.get(path.resolve())


def acquire_snapshot(inventory: FileInventory, *, extra_paths: list[Path] | None = None) -> RepositorySnapshot:
    """Read the contents of everything *inventory* enumerates, once.

    Takes the inventory rather than sweeping for one itself, so that a pass has exactly one sweep and
    it is the port's — the two-sweep defect is not reachable by construction.

    ``extra_paths`` carries files the inventory does not enumerate but a pass still verifies —
    documents, which live outside it.
    """
    contents: dict[Path, str] = {}
    enumerated = (inventory.rel_to_path[rel] for rel in inventory.ordered_paths if rel in inventory.rel_to_path)
    for path in [*(p.resolve() for p in enumerated), *(p.resolve() for p in extra_paths or [])]:
        try:
            contents[path] = path.read_text(encoding="utf-8")
        except OSError:
            # Left out deliberately: the rule that reads it reports E001 against the real error,
            # which is a finding about the repository rather than about acquisition.
            continue
    return RepositorySnapshot(inventory=inventory, contents=contents)
