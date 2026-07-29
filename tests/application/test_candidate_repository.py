"""WU-0.5: CandidateRepository — overlay semantics and aggregate diagram replacement.

Acceptance criteria from the TASKS spec:
- Within one transaction adding CLF@… to diagram A, get_entity returns it before index refresh.
- Deleting an entity returns None despite it being in the live base.
- Replacing a diagram that owned CLF-A+CLF-B with one owning only CLF-A makes get_entity("CLF-B") None
  without CLF-B being in deleted_ids.
- Deleting the host diagram removes all its children.
- Replacement that changes local connections but keeps classifier ids preserves entities.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from src.application.candidate_repository import (
    CandidateRepository,
    _OverlayCandidateRepository,
    candidate_with,
)
from src.domain.ontology_representation.artifact_types import DiagramRecord, EntityRecord

_DIAG_TYPE = "datatype"
_DIAG_PATH = Path("/fake/diag.md")


def _entity(artifact_id: str, host_diagram_id: str | None = None, name: str = "E") -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="classifier",
        name=name,
        version="0.1.0",
        status="active",
        domain=_DIAG_TYPE,
        subdomain="classifier",
        path=_DIAG_PATH,
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=name,
        display_alias=artifact_id,
        host_diagram_id=host_diagram_id,
    )


def _diag(artifact_id: str, extra: dict | None = None) -> DiagramRecord:
    return DiagramRecord(
        artifact_id=artifact_id,
        artifact_type=_DIAG_TYPE,
        diagram_type=_DIAG_TYPE,
        name=artifact_id,
        version="0.1.0",
        status="active",
        path=_DIAG_PATH,
        extra=extra or {},
    )


class _StubBase:
    """Minimal stub implementing CandidateRepository for testing."""

    def __init__(
        self,
        entities: list[EntityRecord] | None = None,
        diagrams: list[DiagramRecord] | None = None,
    ) -> None:
        self._entities: dict[str, EntityRecord] = {e.artifact_id: e for e in (entities or [])}
        self._diagrams: dict[str, DiagramRecord] = {d.artifact_id: d for d in (diagrams or [])}

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._entities.get(artifact_id)

    def get_diagram(self, artifact_id: str) -> DiagramRecord | None:
        return self._diagrams.get(artifact_id)

    def list_entities(
        self,
        *,
        artifact_type: str | None = None,
        domain: str | None = None,
        status: str | None = None,
    ) -> list[EntityRecord]:
        return [
            e for e in self._entities.values()
            if (artifact_type is None or e.artifact_type == artifact_type)
            and (domain is None or e.domain == domain)
            and (status is None or e.status == status)
        ]

    def list_diagrams(
        self,
        *,
        diagram_type: str | None = None,
        status: str | None = None,
    ) -> list[DiagramRecord]:
        return [
            d for d in self._diagrams.values()
            if (diagram_type is None or d.diagram_type == diagram_type)
            and (status is None or d.status == status)
        ]

    def scope_for_path(self, path: Path) -> Literal["enterprise", "engagement", "unknown"]:
        return "engagement"


# ── Structural checks ─────────────────────────────────────────────────────────


def test_stub_base_satisfies_protocol():
    assert isinstance(_StubBase(), CandidateRepository)


def test_overlay_repo_satisfies_protocol():
    from src.application.candidate_repository import _Overlay

    repo = _OverlayCandidateRepository(_StubBase(), _Overlay(additions={}, deletions=frozenset()))
    assert isinstance(repo, CandidateRepository)


# ── candidate_with: new entity visible before index refresh ───────────────────


def test_new_entity_visible_in_candidate():
    """Adding CLF@… to a diagram makes it visible via get_entity before index refresh."""
    new_diag = _diag("DT-A", extra={
        "diagram-entities": {
            "classifier": [{"id": "CLF@1.ab.x", "label": "X"}],
        }
    })
    base = _StubBase(diagrams=[])
    candidate = candidate_with(
        base,
        changed_diagrams=[new_diag],
        workspace_types={"datatype": frozenset({"classifier"})},
    )

    result = candidate.get_entity("CLF@1.ab.x")
    assert result is not None
    assert result.artifact_id == "CLF@1.ab.x"
    assert result.host_diagram_id == "DT-A"


# ── candidate_with: deletion hides entity ────────────────────────────────────


def test_deleted_entity_hidden():
    """Deleting CLF@… returns None even though it exists in the base."""
    clf = _entity("CLF@1.ab.y", host_diagram_id="DT-B")
    base = _StubBase(entities=[clf])
    candidate = candidate_with(base, deleted_ids=frozenset({"CLF@1.ab.y"}))

    assert candidate.get_entity("CLF@1.ab.y") is None


# ── candidate_with: diagram replacement child suppression ─────────────────────


_WS = {"datatype": frozenset({"classifier"})}


def test_replaced_diagram_drops_removed_child():
    """Replace diagram A (had CLF-A + CLF-B) with one having only CLF-A → CLF-B returns None."""
    clf_a = _entity("CLF@1.ab.a", host_diagram_id="DT-A")
    clf_b = _entity("CLF@1.ab.b", host_diagram_id="DT-A")
    old_diag = _diag("DT-A", extra={
        "diagram-entities": {
            "classifier": [
                {"id": "CLF@1.ab.a", "label": "A"},
                {"id": "CLF@1.ab.b", "label": "B"},
            ]
        }
    })
    new_diag = _diag("DT-A", extra={
        "diagram-entities": {
            "classifier": [{"id": "CLF@1.ab.a", "label": "A"}]
        }
    })
    base = _StubBase(entities=[clf_a, clf_b], diagrams=[old_diag])
    candidate = candidate_with(base, changed_diagrams=[new_diag], workspace_types=_WS)

    assert candidate.get_entity("CLF@1.ab.a") is not None
    assert candidate.get_entity("CLF@1.ab.b") is None


def test_replaced_diagram_keeps_retained_child():
    """A child retained in the replacement is accessible via the new extraction."""
    clf_a = _entity("CLF@1.ab.a", host_diagram_id="DT-A")
    old_diag = _diag("DT-A", extra={
        "diagram-entities": {"classifier": [{"id": "CLF@1.ab.a", "label": "A"}]}
    })
    new_diag = _diag("DT-A", extra={
        "diagram-entities": {"classifier": [{"id": "CLF@1.ab.a", "label": "A renamed"}]}
    })
    base = _StubBase(entities=[clf_a], diagrams=[old_diag])
    candidate = candidate_with(base, changed_diagrams=[new_diag], workspace_types=_WS)

    result = candidate.get_entity("CLF@1.ab.a")
    assert result is not None
    assert result.name == "A renamed"


# ── candidate_with: host diagram deletion removes children ────────────────────


def test_host_diagram_deletion_removes_children():
    """Deleting the host diagram removes all its entity children."""
    clf = _entity("CLF@1.ab.z", host_diagram_id="DT-C")
    diag = _diag("DT-C")
    base = _StubBase(entities=[clf], diagrams=[diag])
    candidate = candidate_with(base, deleted_ids=frozenset({"DT-C"}))

    assert candidate.get_entity("CLF@1.ab.z") is None
    assert candidate.get_diagram("DT-C") is None


# ── candidate_with: connection-change keeps classifier ids ────────────────────


def test_replacement_with_changed_connections_keeps_classifier_ids():
    """Replacing a diagram that changes local connections but keeps classifier ids preserves them."""
    clf = _entity("CLF@1.ab.p", host_diagram_id="DT-D")
    old_diag = _diag("DT-D", extra={
        "diagram-entities": {
            "classifier": [{"id": "CLF@1.ab.p", "label": "P"}]
        },
        "connections": [{"source": "CLF@1.ab.p", "target": "CLF@1.ab.q", "conn_type": "has-attribute"}],
    })
    new_diag = _diag("DT-D", extra={
        "diagram-entities": {
            "classifier": [{"id": "CLF@1.ab.p", "label": "P"}]
        },
        "connections": [],
    })
    base = _StubBase(entities=[clf], diagrams=[old_diag])
    candidate = candidate_with(base, changed_diagrams=[new_diag], workspace_types=_WS)

    assert candidate.get_entity("CLF@1.ab.p") is not None


# ── list_entities filters ─────────────────────────────────────────────────────


def test_list_entities_excludes_deletions():
    """list_entities omits deleted entities even when base returns them."""
    e1 = _entity("CLF@1.ab.1", host_diagram_id="DT-E")
    e2 = _entity("CLF@1.ab.2", host_diagram_id="DT-E")
    base = _StubBase(entities=[e1, e2])
    candidate = candidate_with(base, deleted_ids=frozenset({"CLF@1.ab.1"}))

    ids = {e.artifact_id for e in candidate.list_entities()}
    assert "CLF@1.ab.1" not in ids
    assert "CLF@1.ab.2" in ids


def test_list_entities_includes_new_additions():
    """list_entities includes entities extracted from changed diagrams."""
    new_diag = _diag("DT-F", extra={
        "diagram-entities": {
            "classifier": [{"id": "CLF@1.ab.new", "label": "New"}]
        }
    })
    base = _StubBase()
    candidate = candidate_with(base, changed_diagrams=[new_diag], workspace_types=_WS)

    ids = {e.artifact_id for e in candidate.list_entities()}
    assert "CLF@1.ab.new" in ids


# ── list_diagrams filters ─────────────────────────────────────────────────────


def test_list_diagrams_excludes_deleted():
    """list_diagrams omits deleted diagrams."""
    from src.application.candidate_repository import _Overlay

    diag = _diag("DT-G")
    base = _StubBase(diagrams=[diag])
    repo = _OverlayCandidateRepository(base, _Overlay(additions={}, deletions=frozenset({"DT-G"})))

    assert repo.list_diagrams() == []


def test_list_diagrams_includes_additions():
    """list_diagrams includes diagrams added via overlay."""
    from src.application.candidate_repository import _Overlay

    new_diag = _diag("DT-H")
    base = _StubBase()
    repo = _OverlayCandidateRepository(base, _Overlay(additions={"DT-H": new_diag}, deletions=frozenset()))

    result = repo.list_diagrams()
    assert any(d.artifact_id == "DT-H" for d in result)
