"""Round-trip persistence tests for entity frontmatter `specialization` and the
connection per-connection metadata block — including the "editing one connection
preserves the sibling's metadata block byte-exact" acceptance criterion.

Uses the real ArtifactRegistry/ArtifactVerifier (shared_artifact_index-backed), matching
the established pattern in test_connection_add_errors.py, rather than a hand-rolled fake —
add_connection's semantic checks need real registry surface (entity_ids(), etc.), and its
write path verifies content against the real verifier (incl. the new specialization
rules), so fixture entity/connection types must be real, catalog-valid combinations, not
placeholders — a first draft using `archimate-assignment` between two `requirement`
entities with an invented "money-flow" slug failed exactly the way it should have: E126
(assignment not permitted requirement->requirement) and E161 (money-flow isn't a real
specialization) both fired, rolling the write back. Fixed by using the two real connection
specializations the archimate_4 module actually ships (`responsibility-assignment`,
`behavior-assignment`, both under `archimate-assignment`) and a real permitted pair
(`grouping -> requirement`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifact_parsing import parse_entity, parse_outgoing_file
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.artifact_index.service import ArtifactIndex
from src.infrastructure.write.artifact_write.connection import add_connection
from src.infrastructure.write.artifact_write.connection_edit import edit_connection
from src.infrastructure.write.artifact_write.entity import create_entity
from src.infrastructure.write.artifact_write.entity_edit import edit_entity


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity_md(artifact_id: str, name: str, artifact_type: str) -> str:
    return (
        f"---\nartifact-id: {artifact_id}\nartifact-type: {artifact_type}\nname: \"{name}\"\n"
        "version: 0.1.0\nstatus: draft\nlast-updated: '2026-01-01'\n---\n"
        f"<!-- §content -->\n\n## {name}\n\n## Properties\n\n| Attribute | Value |\n|---|---|\n"
        "| (none) | (none) |\n"
    )


def _build_deps(repo_root: Path) -> tuple[ArtifactRegistry, ArtifactVerifier]:
    """A fresh (non-cached) ArtifactIndex each call — tests that write then immediately
    need to see that write through a *new* registry must not reuse a `shared_artifact_index`
    instance, which caches per repo root independent of what's currently on disk."""
    registry = ArtifactRegistry(ArtifactIndex([repo_root]))
    verifier = ArtifactVerifier(registry, catalogs=build_runtime_catalogs(get_module_registry()))
    return registry, verifier


@pytest.fixture()
def repo(tmp_path: Path):
    root = tmp_path / "engagements" / "ENG-SPEC" / "architecture-repository"
    src = "GRP@1000000300.SrcEnt.src"
    tgt = "REQ@1000000301.TgtEnt1.tgt"
    tgt2 = "REQ@1000000302.TgtEnt2.tgt2"
    _write(root / "model" / "common" / "grouping" / f"{src}.md", _entity_md(src, "Src", "grouping"))
    _write(root / "model" / "motivation" / "requirement" / f"{tgt}.md", _entity_md(tgt, "Tgt", "requirement"))
    _write(root / "model" / "motivation" / "requirement" / f"{tgt2}.md", _entity_md(tgt2, "Tgt2", "requirement"))
    return root, src, tgt, tgt2


def _add(root, registry, verifier, *, source, target, specialization=None):
    add_connection(
        repo_root=root, registry=registry, verifier=verifier, clear_repo_caches=lambda p: None,
        source_entity=source, connection_type="archimate-assignment", target_entity=target,
        description=None, version="0.1.0", status="draft", last_updated="2026-01-01",
        dry_run=False, specialization=specialization,
    )


def _outgoing_path(root: Path, src: str) -> Path:
    return root / "model" / "common" / "grouping" / f"{src}.outgoing.md"


def test_add_connection_with_specialization_round_trips(repo) -> None:
    root, src, tgt, _ = repo
    registry, verifier = _build_deps(root)
    _add(root, registry, verifier, source=src, target=tgt, specialization="responsibility-assignment")

    (record,) = parse_outgoing_file(_outgoing_path(root, src))
    assert record.specialization == "responsibility-assignment"


def test_two_connections_carry_different_specializations(repo) -> None:
    root, src, tgt, tgt2 = repo
    registry, verifier = _build_deps(root)
    _add(root, registry, verifier, source=src, target=tgt, specialization="responsibility-assignment")
    _add(root, registry, verifier, source=src, target=tgt2, specialization="behavior-assignment")

    records = parse_outgoing_file(_outgoing_path(root, src))
    by_target = {r.target: r.specialization for r in records}
    assert by_target == {tgt: "responsibility-assignment", tgt2: "behavior-assignment"}


def test_editing_one_connection_preserves_sibling_metadata_block_byte_exact(repo) -> None:
    root, src, tgt, tgt2 = repo
    registry, verifier = _build_deps(root)
    _add(root, registry, verifier, source=src, target=tgt, specialization="responsibility-assignment")
    _add(root, registry, verifier, source=src, target=tgt2, specialization="behavior-assignment")
    outgoing = _outgoing_path(root, src)
    before = outgoing.read_text(encoding="utf-8")
    sibling_marker = f"### archimate-assignment → {tgt2}"
    sibling_before = before[before.index(sibling_marker) :]

    edit_connection(
        repo_root=root, registry=registry, verifier=verifier, clear_repo_caches=lambda p: None,
        source_entity=src, target_entity=tgt, connection_type="archimate-assignment",
        description="now has a description", dry_run=False,
    )

    after = outgoing.read_text(encoding="utf-8")
    sibling_after = after[after.index(sibling_marker) :]
    assert sibling_after == sibling_before
    records = parse_outgoing_file(outgoing)
    by_target = {r.target: r for r in records}
    assert by_target[tgt].content_text == "now has a description"
    assert by_target[tgt2].specialization == "behavior-assignment"


def test_edit_connection_clears_specialization_with_empty_string(repo) -> None:
    root, src, tgt, _ = repo
    registry, verifier = _build_deps(root)
    _add(root, registry, verifier, source=src, target=tgt, specialization="responsibility-assignment")
    outgoing = _outgoing_path(root, src)

    edit_connection(
        repo_root=root, registry=registry, verifier=verifier, clear_repo_caches=lambda p: None,
        source_entity=src, target_entity=tgt, connection_type="archimate-assignment",
        specialization="", dry_run=False,
    )

    (record,) = parse_outgoing_file(outgoing)
    assert record.specialization == ""
    assert "```yaml" not in outgoing.read_text(encoding="utf-8")


def test_entity_create_and_parse_round_trip_specialization(tmp_path: Path) -> None:
    root = tmp_path / "engagements" / "ENG-SPEC2" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    registry, verifier = _build_deps(root)

    result = create_entity(
        repo_root=root, verifier=verifier, clear_repo_caches=lambda p: None,
        artifact_type="collaboration", name="Cross-team Incident Response", summary=None, properties=None,
        notes=None, artifact_id="COL@1000000310.CrossTeam.cross-team-incident-response", version="0.1.0",
        status="draft", last_updated="2026-01-01", dry_run=False, specialization="business-collaboration",
    )
    assert result.wrote, result.verification

    record = parse_entity(result.path, root / "model", domain_names=frozenset({"business"}))
    assert record is not None
    assert record.specialization == "business-collaboration"


def test_entity_edit_updates_specialization_preserving_other_fields(tmp_path: Path) -> None:
    root = tmp_path / "engagements" / "ENG-SPEC3" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    registry, verifier = _build_deps(root)
    eid = "COL@1000000320.CrossTeam2.cross-team-incident-response-2"
    create_entity(
        repo_root=root, verifier=verifier, clear_repo_caches=lambda p: None,
        artifact_type="collaboration", name="Cross-team Incident Response", summary=None, properties=None,
        notes=None, artifact_id=eid, version="0.1.0", status="draft", last_updated="2026-01-01",
        dry_run=False, specialization="business-collaboration",
    )
    entity_file = root / "model" / "common" / "collaboration" / f"{eid}.md"
    registry2, verifier2 = _build_deps(root)

    edit_entity(
        repo_root=root, registry=registry2, verifier=verifier2, clear_repo_caches=lambda p: None,
        artifact_id=eid, specialization="application-collaboration", dry_run=False,
    )

    record = parse_entity(entity_file, root / "model", domain_names=frozenset({"common"}))
    assert record is not None
    assert record.specialization == "application-collaboration"
    assert record.name == "Cross-team Incident Response"
