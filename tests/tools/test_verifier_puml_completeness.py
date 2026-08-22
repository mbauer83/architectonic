"""The completeness invariant: what a diagram body expresses, its bindings must own.

The reconcile treats ``connection-ids-used`` as authoritative and deletes what is not listed,
so a relation drawn but unbound is data loss waiting for the next refresh — and until this rule
existed, ``artifact_verify`` reported such a repository clean. These tests fix the contract:

* a drawn relation whose pair is model-backed must be listed (E316),
* a drawn arrow no model connection backs is reported (E317),
* an arrow endpoint resolving to no entity at all is reported (E314) — previously a silent
  skip in ``infer_connections_from_puml``,
* an entity the body touches must be listed in entity-ids-used / diagram-entities (E315),
* generator-visual nesting (flow-through events, junctions) stays exempt from E317,
* and the rule guards exactly the reconcile-owned diagrams, nothing else.

Also here: the delegation contract for ``_infer_reference_ids_from_puml`` — it must read
relations through the ONE shared parser, so a hand-supplied body drawn with bare arrows (the
renderer's own output form) binds the connections it draws instead of silently binding none.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from src.application.verification._verifier_rules_puml_completeness import (
    check_diagram_relation_completeness,
)
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.artifact_id import stable_conn_id as _stable
from src.infrastructure.artifact_index import shared_artifact_index

ALPHA = "REQ@1000000000.AaaAaa.alpha"
BETA = "REQ@1000000001.BbbBbb.beta"
GAMMA = "REQ@1000000002.CccCcc.gamma"
INFLUENCE = f"{ALPHA}---{BETA}@@archimate-influence"
COMPOSITION = f"{ALPHA}---{GAMMA}@@archimate-composition"


def _stable_set(connection_ids: list[str] | None) -> set[str]:
    return {_stable(c) for c in connection_ids or []}


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


def _stereo_map():
    return _catalogs().ontology.archimate_stereotype_to_connection_type()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity(artifact_id: str, name: str) -> str:
    prefix, rand = artifact_id.split("@")[0], artifact_id.split(".")[1]
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-07-29'
---

<!-- §content -->

## {name}

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: {prefix}_{rand}
```
"""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    req_dir = root / "model" / "motivation" / "requirement"
    for eid, name in ((ALPHA, "Alpha"), (BETA, "Beta"), (GAMMA, "Gamma")):
        _write(req_dir / f"{eid}.md", _entity(eid, name))
    _write(
        req_dir / f"{ALPHA}.outgoing.md",
        f"""\
---
source-entity: {ALPHA}
version: 0.1.0
status: draft
last-updated: '2026-07-29'
---

<!-- §connections -->

### archimate-influence → {BETA}

### archimate-composition → {GAMMA}
""",
    )
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _fm(
    *,
    entity_ids: list[str] | None = None,
    connection_ids: list[str] | None = None,
    diagram_type: str = "archimate-motivation",
    **extra: object,
) -> dict:
    fm: dict = {
        "artifact-id": "ARC@1000000009.DiagAa.view",
        "artifact-type": "diagram",
        "diagram-type": diagram_type,
        "entity-ids-used": [ALPHA, BETA, GAMMA] if entity_ids is None else entity_ids,
        "connection-ids-used": [] if connection_ids is None else connection_ids,
    }
    fm.update(extra)
    return fm


def _issues(repo: Path, body: str, fm: dict) -> list:
    registry = ArtifactRegistry(shared_artifact_index(repo))
    result = VerificationResult(path=repo / "diagram-catalog" / "diagrams" / "view.puml", file_type="diagram")
    check_diagram_relation_completeness(
        body, fm, registry, result, "view.puml",
        stereotype_map=_stereo_map(), diagram_type_catalog=_catalogs().diagram_types,
    )
    return result.issues


def _codes(issues: list) -> list[str]:
    return [i.code for i in issues]


class TestExpressedRelationsMustBeBound:
    def test_a_listed_relation_raises_nothing(self, repo: Path) -> None:
        issues = _issues(repo, "REQ_AaaAaa ..> REQ_BbbBbb\n", _fm(connection_ids=[INFLUENCE]))
        assert issues == []

    def test_a_drawn_but_unlisted_relation_is_an_error_naming_the_candidate(self, repo: Path) -> None:
        """The original data-loss scenario: the renderer's own bare-arrow form, drawn but not
        bound — the next reconcile would drop it without a trace."""
        issues = _issues(repo, "REQ_AaaAaa ..> REQ_BbbBbb\n", _fm(connection_ids=[]))
        assert _codes(issues) == ["E316"]
        assert "archimate-influence" in issues[0].message  # the candidate is named for repair

    def test_a_listed_relation_satisfies_regardless_of_id_form(self, repo: Path) -> None:
        """connection-ids-used may carry the slug-free short form; stable comparison must agree."""
        short = "REQ@1000000000.AaaAaa---REQ@1000000001.BbbBbb@@archimate-influence"
        assert _issues(repo, "REQ_AaaAaa ..> REQ_BbbBbb\n", _fm(connection_ids=[short])) == []

    def test_an_arrow_no_model_connection_backs_is_reported(self, repo: Path) -> None:
        issues = _issues(repo, "REQ_BbbBbb --> REQ_CccCcc\n", _fm())
        assert _codes(issues) == ["E317"]

    def test_an_arrow_whose_alias_resolves_to_no_entity_is_reported_not_skipped(self, repo: Path) -> None:
        """This exact case was a silent skip in infer_connections_from_puml."""
        issues = _issues(repo, "REQ_AaaAaa --> GHO_stAls\n", _fm())
        assert _codes(issues) == ["E314"]
        assert "GHO_stAls" in issues[0].message

    def test_the_same_drawn_relation_is_reported_once(self, repo: Path) -> None:
        body = "REQ_AaaAaa ..> REQ_BbbBbb\nREQ_AaaAaa ..> REQ_BbbBbb\n"
        assert _codes(_issues(repo, body, _fm(connection_ids=[]))) == ["E316"]


class TestTouchedEntitiesMustBeBound:
    def test_an_entity_the_body_draws_but_never_lists_is_an_error(self, repo: Path) -> None:
        issues = _issues(
            repo, "REQ_AaaAaa ..> REQ_BbbBbb\n",
            _fm(entity_ids=[ALPHA], connection_ids=[INFLUENCE]),
        )
        assert _codes(issues) == ["E315"]
        assert "REQ_BbbBbb" in issues[0].message

    def test_an_empty_diagram_entities_mapping_does_not_gate_the_rule_out(self, repo: Path) -> None:
        # Per the diagram-body-ownership note, an empty diagram-entities dict does not make a
        # diagram standalone — the reconcile still owns it, so the invariant still holds.
        issues = _issues(
            repo, "REQ_AaaAaa ..> REQ_BbbBbb\n",
            _fm(entity_ids=[ALPHA], connection_ids=[INFLUENCE]) | {"diagram-entities": {}},
        )
        assert _codes(issues) == ["E315"]


class TestNestingIsReadButVisualNestingIsNotPunished:
    def test_model_backed_nesting_must_be_listed(self, repo: Path) -> None:
        """The containment blind spot that flattened conformance-review: composition is drawn
        as nesting, with no arrow at all."""
        body = (
            'rectangle "Alpha" <<requirement>> as REQ_AaaAaa {\n'
            '  rectangle "Gamma" <<requirement>> as REQ_CccCcc\n'
            "}\n"
        )
        issues = _issues(repo, body, _fm(connection_ids=[]))
        assert _codes(issues) == ["E316"]
        assert "archimate-composition" in issues[0].message

    def test_unbacked_nesting_is_legitimate_generated_output(self, repo: Path) -> None:
        """The generator nests flow-through events and junction components with no model
        relation behind them (build_visual_nesting); that must not fail verification."""
        body = (
            'rectangle "Beta" <<requirement>> as REQ_BbbBbb {\n'
            '  rectangle "Gamma" <<requirement>> as REQ_CccCcc\n'
            "}\n"
        )
        assert _issues(repo, body, _fm()) == []

    def test_an_aliased_grouping_rectangle_is_not_a_relation_endpoint(self, repo: Path) -> None:
        body = (
            'rectangle "Requirements" <<CommonGrouping>> as GRPA_1 {\n'
            '  rectangle "Alpha" <<requirement>> as REQ_AaaAaa\n'
            "}\n"
        )
        assert _issues(repo, body, _fm()) == []


class TestTheRuleGuardsExactlyTheReconcileOwnedDiagrams:
    UNBOUND_ARROW = "REQ_AaaAaa ..> REQ_BbbBbb\n"

    def test_a_standalone_diagram_is_not_checked(self, repo: Path) -> None:
        fm = _fm(connection_ids=[]) | {"diagram-entities": {"requirement": [{"id": GAMMA}]}}
        assert _issues(repo, self.UNBOUND_ARROW, fm) == []

    def test_a_diagram_owned_type_speaks_its_own_vocabulary(self, repo: Path) -> None:
        fm = _fm(connection_ids=[], diagram_type="sequence")
        assert _issues(repo, self.UNBOUND_ARROW, fm) == []

    def test_a_projector_owned_diagram_is_not_checked(self, repo: Path) -> None:
        fm = _fm(connection_ids=[]) | {
            "bindings": [{
                "id": "b1", "correspondence_kind": "scoped-by",
                "subject": {"kind": "diagram"}, "target": {"entity_id": ALPHA},
            }]
        }
        assert _issues(repo, self.UNBOUND_ARROW, fm) == []

    def test_a_manual_layout_diagram_is_held_to_the_same_error(self, repo: Path) -> None:
        """Severity is uniform: the real manual-layout diagrams pass the rule, so no
        per-flag leniency was needed or granted."""
        fm = _fm(connection_ids=[]) | {"manual-layout": True}
        assert _codes(_issues(repo, self.UNBOUND_ARROW, fm)) == ["E316"]


class TestTheVerifierSurfacesTheRule:
    def test_verify_diagram_file_reports_the_unbound_relation(self, repo: Path) -> None:
        diagram_path = repo / "diagram-catalog" / "diagrams" / "ARC@1000000009.DiagAa.view.puml"
        _write(
            diagram_path,
            f"""\
---
artifact-id: ARC@1000000009.DiagAa.view
artifact-type: diagram
name: "View"
version: 0.1.0
status: draft
diagram-type: archimate-motivation
entity-ids-used:
- {ALPHA}
- {BETA}
last-updated: '2026-07-29'
---
@startuml view
title View
rectangle "Alpha" <<requirement>> as REQ_AaaAaa
rectangle "Beta" <<requirement>> as REQ_BbbBbb
REQ_AaaAaa ..> REQ_BbbBbb
@enduml
""",
        )
        registry = ArtifactRegistry(shared_artifact_index(repo))
        verifier = ArtifactVerifier(registry, check_puml_syntax=False, catalogs=_catalogs())
        result = verifier.verify_diagram_file(diagram_path)
        assert any(i.code == "E316" for i in result.issues), [i.message for i in result.issues]


class TestInferReadsThroughTheSharedParser:
    """Delegation contract for _infer_reference_ids_from_puml (the former blind copy)."""

    def test_a_bare_arrow_infers_the_connection_it_draws(self, repo: Path) -> None:
        """A hand-supplied body in the renderer's own output form must bind what it draws;
        the blind copy inferred nothing here, which is how bodies outran their bindings."""
        from src.infrastructure.write.artifact_write.diagram_references import (
            _infer_reference_ids_from_puml,
        )

        _entity_ids, connection_ids, _undecided = _infer_reference_ids_from_puml(
            repo, "REQ_AaaAaa ..> REQ_BbbBbb\n"
        )
        assert _stable(INFLUENCE) in _stable_set(connection_ids)

    def test_containment_nesting_infers_the_composition_it_states(self, repo: Path) -> None:
        from src.infrastructure.write.artifact_write.diagram_references import (
            _infer_reference_ids_from_puml,
        )

        body = (
            'rectangle "Alpha" <<requirement>> as REQ_AaaAaa {\n'
            '  rectangle "Gamma" <<requirement>> as REQ_CccCcc\n'
            "}\n"
        )
        entity_ids, connection_ids, _undecided = _infer_reference_ids_from_puml(repo, body)
        assert entity_ids is not None and {ALPHA, GAMMA} <= set(entity_ids)
        assert _stable(COMPOSITION) in _stable_set(connection_ids)

    def test_a_typed_relation_still_infers_exactly_as_before(self, repo: Path) -> None:
        from src.infrastructure.write.artifact_write.diagram_references import (
            _infer_reference_ids_from_puml,
        )

        _entity_ids, connection_ids, _undecided = _infer_reference_ids_from_puml(
            repo, "REQ_AaaAaa ..> REQ_BbbBbb : <<influence>>\n"
        )
        assert _stable(INFLUENCE) in _stable_set(connection_ids)
