"""Scratchpads on disk: one YAML document per scratchpad, git-diffable on purpose.

**Not** frontmatter-plus-body. Frontmatter exists to separate metadata from prose, and a scratchpad
has no prose body — its prose lives in fields. Pretending otherwise would add ceremony every reader
and every parser then has to strip. The precedent is the diagram, which already proves the
repository tolerates a body that is not markdown so long as identity and metadata are conventional.

Two properties make a scratchpad reviewable rather than merely stored, and both are this module's
responsibility because both are about serialisation rather than about the aggregate:

* **stable order** — every collection is written sorted by id, so re-saving an unchanged scratchpad
  produces an unchanged file, and a diff shows what moved rather than how the dict happened to
  iterate;
* **layout last, and snapped** — geometry is one block at the end, on the grid the domain defines,
  so an afternoon of tidying and an afternoon of thinking land in different parts of the file.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from src.application.scratchpad.document import from_document, to_document
from src.application.scratchpad.ports import (
    ScratchpadNotFoundError,
    ScratchpadSummary,
    ScratchpadVersionConflictError,
)
from src.domain.artifact_id import stable_id
from src.domain.repository.groups import UNCATEGORIZED as _UNCATEGORIZED
from src.domain.repository.repo_layout import SCRATCHPAD_SUFFIX, SCRATCHPADS
from src.domain.scratchpad import Scratchpad
from src.domain.yaml_documents import parse_yaml

#: The file suffix, re-exported from the layout module so this repository and the index scan for
#: the same thing. Every caller already asks this module for it.
SUFFIX = SCRATCHPAD_SUFFIX

#: What a scratchpad's version is before its first write, so the file it is created as carries the
#: first bump of it. Nothing before a create is stored, so this is the store's own starting point
#: rather than anything a caller supplies.
_UNSTORED_VERSION = "0.1.0"


def _bump(version: str) -> str:
    """Next patch version. The version is a concurrency token first and a version second, so it
    only has to move on every write — but it moves the way the rest of the repository's do."""
    parts = version.split(".")
    if len(parts) == 3 and parts[2].isdigit():
        return f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
    return "0.1.1"


class YamlScratchpadRepository:
    """`ScratchpadRepositoryPort` over `scratchpads/<group>/<id>.scratchpad.yaml`."""

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root / SCRATCHPADS

    # ── Reading ──────────────────────────────────────────────────────────────

    def _paths(self) -> list[Path]:
        return sorted(self._root.rglob(f"*{SUFFIX}")) if self._root.is_dir() else []

    def _path_for(self, artifact_id: str) -> Path | None:
        short = stable_id(artifact_id)
        for path in self._paths():
            name = path.name[: -len(SUFFIX)]
            if name == artifact_id or stable_id(name) == short:
                return path
        return None

    def list_scratchpads(self, *, group: str | None = None, status: str | None = None) -> list[ScratchpadSummary]:
        summaries: list[ScratchpadSummary] = []
        for path in self._paths():
            raw = _read_yaml(path)
            if not raw:
                continue
            found_group = path.parent.name if path.parent != self._root else _UNCATEGORIZED
            found_status = str(raw.get("status") or "draft")
            if group is not None and found_group != group:
                continue
            if status is not None and found_status != status:
                continue
            summaries.append(ScratchpadSummary(
                artifact_id=str(raw.get("artifact-id") or path.name[: -len(SUFFIX)]),
                name=str(raw.get("name") or ""),
                description=str(raw.get("description") or ""),
                status=found_status,
                version=str(raw.get("version") or "0.1.0"),
                group=found_group,
                meta_ontology=str(raw.get("meta-ontology") or "archimate-4"),
                note_count=len(raw.get("notes") or []),
            ))
        return sorted(summaries, key=lambda summary: summary.artifact_id)

    def load(self, artifact_id: str) -> Scratchpad:
        path = self._path_for(artifact_id)
        if path is None:
            raise ScratchpadNotFoundError(f"no scratchpad {artifact_id!r} under {self._root}")
        return from_document(_read_yaml(path))

    def group_of(self, artifact_id: str) -> str:
        path = self._path_for(artifact_id)
        if path is None:
            raise ScratchpadNotFoundError(f"no scratchpad {artifact_id!r} under {self._root}")
        return path.parent.name if path.parent != self._root else _UNCATEGORIZED

    # ── Writing ──────────────────────────────────────────────────────────────

    def save(self, scratchpad: Scratchpad, *, group: str, expected_version: str | None = None) -> Scratchpad:
        """Store the aggregate, unless storing it would change nothing.

        **The version stored is the store's, never the caller's.** The token travels beside the
        document — `ScratchpadDocumentWire` says the in-document `version` is "read back and
        ignored here" — so bumping the caller's copy of it made the store follow whatever a client
        happened to send: one that omitted it drove the stored version *backwards*, after which
        every writer's token validated forever and the conflict check protected nobody.

        **A save that stores what is already stored is not a write.** Geometry snaps to the grid,
        so a drag too small to leave its cell arrives as a document byte-identical to the file. That
        cost a trip through the write queue, left a modified file in git with no content change, and
        invalidated every other client's token for a change that never happened. Compared as text
        because that is exactly the question — would this write change the file? — which also
        re-writes a file whose formatting has drifted rather than declaring it unchanged.
        """
        existing = self._path_for(scratchpad.artifact_id)
        on_disk = existing.read_text(encoding="utf-8") if existing is not None else None
        stored_version = _version_of(on_disk)
        if stored_version is not None and expected_version != stored_version:
            raise ScratchpadVersionConflictError(
                scratchpad.artifact_id, expected_version or "(none)", stored_version
            )
        current = replace(
            scratchpad,
            version=stored_version or _UNSTORED_VERSION,
            layout=scratchpad.layout.snapped(),
        )
        current.validate()
        target = self._root / group / f"{current.artifact_id}{SUFFIX}"
        # A re-home writes even an identical document, because the file has to move.
        if existing == target and serialize(current) == on_disk:
            return current
        stored = replace(current, version=_bump(current.version))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialize(stored), encoding="utf-8")
        # A re-home is a move, not a copy: leaving the old file behind would make one scratchpad
        # answer to two ids the moment either is edited.
        if existing is not None and existing != target:
            existing.unlink(missing_ok=True)
        _reindex(target, existing)
        return stored

    def delete(self, artifact_id: str) -> None:
        path = self._path_for(artifact_id)
        if path is None:
            raise ScratchpadNotFoundError(f"no scratchpad {artifact_id!r} under {self._root}")
        path.unlink()
        _reindex(path)


def _reindex(*paths: Path | None) -> None:
    """Tell every live index that this file moved, so its notes are findable *now*.

    Here rather than in the REST router or the MCP tool because this is the one place that knows
    which file was written, and a notification each surface has to remember is one a surface
    eventually forgets — which is exactly what happened: the loader and the incremental applier both
    existed, and nothing called them, so a note written on the canvas was searchable only after the
    next full refresh.

    Broadcast rather than applied to one index: MCP write tools resolve a narrower, engagement-only
    index over the same files than the REST layer's combined one, and both have to see the change.
    A scratchpad change deliberately does **not** move the model's read-model generation — see
    `ArtifactIndex.apply_file_changes`.
    """
    from src.infrastructure.artifact_index import notify_paths_changed  # noqa: PLC0415

    changed = [path for path in paths if path is not None]
    if changed:
        notify_paths_changed(changed)


def _version_of(document_text: str | None) -> str | None:
    """The version the store holds, or `None` where it holds nothing yet — which is the difference
    between an update and a create. A stored document with no version reads as the unstored one,
    since that is what it would have been written from."""
    if document_text is None:
        return None
    return str(_document(document_text).get("version") or _UNSTORED_VERSION)


def _document(text: str) -> dict[str, Any]:
    """The stored document. Takes the text rather than the path so `save` can ask what is stored
    and whether writing would change it without reading the same file twice."""
    loaded = parse_yaml(text)
    return loaded if isinstance(loaded, dict) else {}


def _read_yaml(path: Path) -> dict[str, Any]:
    return _document(path.read_text(encoding="utf-8"))


def serialize(scratchpad: Scratchpad) -> str:
    """The document, as YAML. The document shape itself is `application.scratchpad.document` —
    the REST payload speaks the same vocabulary deliberately, and writing that mapping twice would
    make the sameness a coincidence maintained by hand."""
    return str(yaml.safe_dump(to_document(scratchpad), sort_keys=False, allow_unicode=True, width=100))
