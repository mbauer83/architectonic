"""Atomic, version-checked persistence of candidate architectures in the engagement."""
from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from src.application.change_sets.base import record_revision
from src.application.change_sets.candidate_architecture import CandidateArchitecture, MalformedCandidateArchitecture
from src.application.change_sets.candidate_recorded_form import dump_candidate, load_candidate, to_mapping
from src.application.change_sets.ordering import application_order
from src.application.change_sets.stacking import sets_beneath, stack_of
from src.domain.artifact_id import parse_entity_id
from src.domain.repository.artifact_location import artifact_kind
from src.infrastructure.atomic_file import write_atomic

KIND = artifact_kind("candidate-architecture")


def read_candidate_path(path: Path) -> CandidateArchitecture | None:
    try:
        return load_candidate(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


class CandidateConflict(ValueError):
    pass


class CandidateArchitectureStore:
    def __init__(self, root: Path) -> None:
        self.directory = root.joinpath(*KIND.roots[0])

    def path(self, ref: str) -> Path:
        if Path(ref).name != ref or parse_entity_id(ref).prefix != KIND.id_prefix:
            raise MalformedCandidateArchitecture(f"Expected a candidate architecture id, got {ref!r}.")
        path = self.directory / (ref + KIND.suffixes[0])
        if self.directory.is_symlink() or path.is_symlink():
            raise MalformedCandidateArchitecture("A candidate file and its directory must be local repository paths.")
        return path

    def find(self, ref: str) -> CandidateArchitecture | None:
        path = self.path(ref)
        try:
            candidate = load_candidate(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if candidate.id != ref:
            raise MalformedCandidateArchitecture(f"{path.name} declares another candidate, {candidate.id}.")
        return candidate

    def require(self, ref: str) -> CandidateArchitecture:
        found = self.find(ref)
        if found is None:
            raise FileNotFoundError(ref)
        return found

    def list(self) -> list[CandidateArchitecture]:
        return [self.require(KIND.file_identity(p)) for p in sorted(self.directory.glob("*" + KIND.suffixes[0]))]

    @contextmanager
    def _locked(self, ref: str) -> Iterator[None]:
        # Lock the directory itself. Two processes may be updating different members of one parent chain.
        from src.infrastructure.write.artifact_write.boundary import assert_engagement_write_root  # noqa: PLC0415

        directory = self.path(ref).parent
        assert_engagement_write_root(directory.parent)
        directory.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def save(self, candidate: CandidateArchitecture, based_on: str | None) -> str:
        with self._locked(candidate.id):
            old = self.find(candidate.id)
            version = record_revision(to_mapping(candidate))
            if old == candidate:
                return version
            current = record_revision(to_mapping(old)) if old else None
            if current != based_on:
                raise CandidateConflict("The candidate changed. Read its current version before editing it.")
            if old and old.state in {"integrated", "superseded", "rejected"}:
                raise CandidateConflict("A terminal candidate is immutable. Create a new candidate.")
            if old and old.state == "candidate" and old.changes != candidate.changes:
                raise CandidateConflict("Return the candidate to draft before changing its operations.")
            stack = stack_of(candidate, self.find)
            application_order(candidate.changes, beneath=sets_beneath(stack))
            write_atomic(self.path(candidate.id), dump_candidate(candidate))
            return version

    def delete(self, ref: str) -> None:
        """Remove the candidate's file. Whether anything still depends on it is the caller's to ask."""
        with self._locked(ref):
            self.path(ref).unlink()
