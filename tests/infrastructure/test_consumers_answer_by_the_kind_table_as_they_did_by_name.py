"""Each consumer that used to decide by a kind's name gives, per kind, the answer it gave before.

The kind table replaced a `match` or a tuple of names at each of these. Moving a fact onto a row is
only a consolidation if every consumer still answers as it did, so the expectation for each kind
below is the literal the consumer held, kept here after the literal has gone:

* `artifact_verify` inferred `"entity" | "connection" | "diagram" | "document" | "icon"` and turned
  a scratchpad away;
* the save dialog listed an outgoing file as `connections` and every other kind under its own name;
* the verifier's inventory and the bulk inventory each kept `("document", "icon")` for the files
  verified one at a time;
* the index read and applied a change through one arm per kind.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification._verifier_stdlib_adapters import FilesystemInventoryAdapter
from src.domain.repository.artifact_location import ARTIFACT_KIND_NAMES, ArtifactKindName
from src.infrastructure.artifact_index._service_incremental import CHANGE_READERS
from src.infrastructure.artifact_index.service import _CHANGE_APPLIERS
from src.infrastructure.mcp.artifact_mcp.bulk.candidate_inventory import CandidateInventoryPort
from src.infrastructure.mcp.artifact_mcp.verify_tools import _verifiable_kind_at
from src.infrastructure.rest.routers.sync.changes import _classify

#: kind → (a file of it, what `artifact_verify` infers, what the save dialog lists it as,
#:         whether it is verified one file at a time)
_BEFORE: dict[ArtifactKindName, tuple[str, str | None, str, bool]] = {
    "entity": ("projects/core/model/motivation/goal/GOL@1.a.x.md", "entity", "entity", False),
    "connection": ("projects/core/model/motivation/goal/GOL@1.a.x.outgoing.md", "connection", "connections", False),
    "diagram": ("diagram-catalog/diagrams/core/ARC@1.a.x.puml", "diagram", "diagram", False),
    "document": ("docs/adr/core/ADR@1.a.x.md", "document", "document", True),
    "icon": ("diagram-catalog/icons/ICO@1.a.x.md", "icon", "icon", True),
    "scratchpad": ("scratchpads/core/SCR@1.a.x.scratchpad.yaml", None, "scratchpad", False),
}

#: Paths the layout gives no kind, and what the save dialog lists each as.
_NO_KIND = {
    "README.md": "file",
    ".arch-repo/config.yaml": "file",
    "diagram-catalog/rendered/core/ARC@1.a.x.svg": "diagram",
    "diagram-catalog/icons/azure/ICO@1.a.x.md": "diagram",
}


def test_every_kind_is_accounted_for_here() -> None:
    assert set(_BEFORE) == set(ARTIFACT_KIND_NAMES)


@pytest.mark.parametrize("kind", ARTIFACT_KIND_NAMES)
def test_artifact_verify_infers_the_kinds_the_verifier_takes(kind: ArtifactKindName, tmp_path: Path) -> None:
    relative, inferred, _listed, _standalone = _BEFORE[kind]

    assert _verifiable_kind_at(tmp_path / relative, [tmp_path]) == inferred


@pytest.mark.parametrize("relative", sorted(_NO_KIND))
def test_artifact_verify_infers_nothing_outside_the_layout(relative: str, tmp_path: Path) -> None:
    assert _verifiable_kind_at(tmp_path / relative, [tmp_path]) is None
    assert _verifiable_kind_at(tmp_path / relative, [tmp_path / "elsewhere"]) is None


@pytest.mark.parametrize("kind", ARTIFACT_KIND_NAMES)
def test_the_save_dialog_lists_each_kind_as_it_did(kind: ArtifactKindName) -> None:
    relative, _inferred, listed, _standalone = _BEFORE[kind]

    assert _classify(relative) == listed


@pytest.mark.parametrize(("relative", "listed"), sorted(_NO_KIND.items()))
def test_the_save_dialog_lists_what_has_no_kind_as_it_did(relative: str, listed: str) -> None:
    assert _classify(relative) == listed


def _repository_holding_one_of_each(root: Path) -> dict[ArtifactKindName, Path]:
    held: dict[ArtifactKindName, Path] = {}
    for kind, (relative, *_rest) in _BEFORE.items():
        held[kind] = root / relative
        held[kind].parent.mkdir(parents=True, exist_ok=True)
        held[kind].write_text("", encoding="utf-8")
    for stray in ("docs/adr/core/picture.png", "diagram-catalog/icons/azure/ICO@2.a.x.md", "README.md"):
        (root / stray).parent.mkdir(parents=True, exist_ok=True)
        (root / stray).write_text("", encoding="utf-8")
    return held


def test_the_verifier_lists_the_kinds_verified_one_file_at_a_time(tmp_path: Path) -> None:
    held = _repository_holding_one_of_each(tmp_path)
    standalone = sorted(held[kind] for kind, (*_rest, alone) in _BEFORE.items() if alone)

    inventory = FilesystemInventoryAdapter()

    assert inventory.list_standalone_artifacts(tmp_path) == standalone
    assert inventory.filter_standalone_artifacts(tmp_path, sorted(tmp_path.rglob("*"))) == standalone


def test_a_repository_without_the_standalone_roots_lists_none(tmp_path: Path) -> None:
    assert FilesystemInventoryAdapter().list_standalone_artifacts(tmp_path) == []


def test_the_bulk_inventory_keeps_the_same_kinds_for_one_file_at_a_time(tmp_path: Path) -> None:
    held = _repository_holding_one_of_each(tmp_path)
    changed = set(tmp_path.rglob("*"))
    # The filter reads no record, so it is given no registry to read one from.
    port = CandidateInventoryPort(registry=None, changed_paths=changed)  # type: ignore[arg-type]

    kept = port.list_standalone_artifacts(tmp_path)

    assert sorted(kept) == sorted(held[kind] for kind, (*_rest, alone) in _BEFORE.items() if alone)


def test_the_index_reads_and_applies_a_change_of_every_kind() -> None:
    """A table keyed by kind has no arm to forget, provided it has an entry per row."""
    assert set(CHANGE_READERS) == set(ARTIFACT_KIND_NAMES)
    assert set(_CHANGE_APPLIERS) == set(ARTIFACT_KIND_NAMES)
