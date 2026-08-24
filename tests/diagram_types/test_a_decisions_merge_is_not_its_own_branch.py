"""W047: a decision's merge edge may not name a step one of its own branches already names.

A decision declares three edges — `step-then`, `step-else`, and a `step-flow` naming the step the
branches converge on once it closes. Pointing that merge edge at a step a branch already names says
two contradictory things at once, and its only observable effect is that the renderer draws that step
and its entire downstream chain twice: once inside the branch, once after the `endif`. Nested
decisions compound it multiplicatively.

Measured on a five-decision diagram carrying four such declarations: the release tail was drawn four
times and one step seven times, at 3205 x 3544 px; with the four edges withheld, once and three times,
at 2910 x 1705. Verification reported 0 errors and 0 warnings throughout — the diagram was valid and
the picture described a workflow that did not exist.

A first diagnosis blamed the graph's cycles. It was wrong, and this test carries the measurement that
settles it: withholding the *cyclic* merge edge changes no count at all.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.diagram_types.activity._contributions import MERGE_TARGET_CONTRIBUTION
from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext


class _Result:
    def __init__(self) -> None:
        self.issues: list[Any] = []


def _ctx(connections: list[dict[str, str]]) -> BaseDiagramVerificationContext:
    return BaseDiagramVerificationContext(
        fm={"connections": connections},
        loc="ACT@1.probe.puml",
        scope="engagement",
        diagram_id="ACT@1.probe",
        allowed_connections=frozenset(),
        allowed_entities=frozenset(),
        catalogs=None,
    )


def _codes(connections: list[dict[str, str]]) -> list[str]:
    result = _Result()
    MERGE_TARGET_CONTRIBUTION.run(None, _ctx(connections), result)
    return [issue.code for issue in result.issues]


def _messages(connections: list[dict[str, str]]) -> list[str]:
    result = _Result()
    MERGE_TARGET_CONTRIBUTION.run(None, _ctx(connections), result)
    return [issue.message for issue in result.issues]


def _decision(name: str, *, then: str, els: str, flow: str | None) -> list[dict[str, str]]:
    edges = [
        {"id": f"t-{name}", "conn_type": "step-then", "source": name, "target": then},
        {"id": f"e-{name}", "conn_type": "step-else", "source": name, "target": els},
    ]
    if flow is not None:
        edges.append({"id": f"m-{name}", "conn_type": "step-flow", "source": name, "target": flow})
    return edges


class TestWhatIsReported:
    def test_a_merge_naming_its_own_then_is_reported(self) -> None:
        codes = _codes(_decision("d_ops", then="s_merge", els="s_contact", flow="s_merge"))

        assert codes == ["W047"]

    def test_a_merge_naming_its_own_else_is_reported(self) -> None:
        """The `m4` shape: the yes-branch loops back and the merge names the no-branch."""
        codes = _codes(_decision("d_code", then="s_dev", els="s_updatepr", flow="s_updatepr"))

        assert codes == ["W047"]

    def test_the_finding_names_the_decision_the_target_and_which_branch(self) -> None:
        """So the reader can fix the declaration without opening the picture."""
        message = _messages(_decision("d_ops", then="s_merge", els="s_contact", flow="s_merge"))[0]

        assert "d_ops" in message
        assert "s_merge" in message
        assert "step-then" in message


class TestWhatIsNot:
    def test_a_genuine_convergence_is_not_reported(self) -> None:
        """The `d_pr` shape, which is the notation used correctly: both branches converge on a step
        neither of them contains, and it is drawn once after the `endif`."""
        assert _codes(_decision("d_pr", then="s_updatepr", els="s_createpr", flow="s_review")) == []

    def test_a_decision_with_no_merge_edge_is_not_reported(self) -> None:
        """Legitimate: both branches end, so there is nothing to converge on."""
        assert _codes(_decision("d_end", then="s_a", els="s_b", flow=None)) == []

    def test_a_flow_between_two_ordinary_steps_is_not_reported(self) -> None:
        """`step-flow` is also how one step follows another; only a *decision's* own merge edge
        colliding with its own branch is the defect."""
        assert _codes([
            {"id": "f1", "conn_type": "step-flow", "source": "s_a", "target": "s_b"},
            {"id": "f2", "conn_type": "step-flow", "source": "s_b", "target": "s_c"},
        ]) == []

    def test_two_decisions_merging_on_the_same_step_are_not_reported(self) -> None:
        """Two decisions may legitimately converge on one step; neither names it in a branch."""
        edges = _decision("d1", then="s_x", els="s_y", flow="s_join")
        edges += _decision("d2", then="s_p", els="s_q", flow="s_join")

        assert _codes(edges) == []


class TestEachOffendingDeclarationIsNamedOnce:
    def test_four_offending_decisions_give_four_findings(self) -> None:
        """The measured case. One finding per declaration, because one declaration is what a person
        removes — not one per drawing, which is what the reader was counting instead."""
        edges: list[dict[str, str]] = []
        edges += _decision("d_ready", then="s_version", els="s_dev", flow="s_version")
        edges += _decision("d_ops", then="s_merge", els="s_contact", flow="s_merge")
        edges += _decision("d_qg", then="s_createrel", els="s_contact", flow="s_createrel")
        edges += _decision("d_code", then="s_dev", els="s_updatepr", flow="s_updatepr")
        edges += _decision("d_pr", then="s_updatepr", els="s_createpr", flow="s_review")

        assert _codes(edges) == ["W047"] * 4

    def test_a_decision_whose_merge_matches_both_branches_is_named_twice(self) -> None:
        """Degenerate but declarable: both branches and the merge on one step. Two contradictions
        stated, so two findings — collapsing them would hide half of what has to change."""
        assert _codes(_decision("d", then="s_x", els="s_x", flow="s_x")) == ["W047", "W047"]


class TestItReadsTheDeclarationNotTheGraph:
    def test_a_cycle_alone_is_not_reported(self) -> None:
        """The corrected diagnosis, pinned. The first reading blamed the graph's back edges; a cyclic
        graph whose merge edges are all honest has nothing wrong with it, and withholding the cyclic
        edge changed no drawing count."""
        edges = _decision("d_ready", then="s_version", els="s_dev", flow="s_review")
        edges += [{"id": "loop", "conn_type": "step-flow", "source": "s_dev", "target": "d_ready"}]

        assert _codes(edges) == []

    @pytest.mark.parametrize("malformed", [
        [{"id": "x", "conn_type": "step-flow", "source": "", "target": "s_a"}],
        [{"id": "x", "conn_type": "step-flow", "source": "d1", "target": ""}],
        ["not a mapping"],
    ])
    def test_a_malformed_declaration_is_skipped_rather_than_crashing(self, malformed: list[Any]) -> None:
        assert _codes(malformed) == []

    def test_a_diagram_with_no_connections_block_is_skipped(self) -> None:
        result = _Result()
        ctx = BaseDiagramVerificationContext(
            fm={}, loc="ACT@1.probe.puml", scope="engagement", diagram_id="ACT@1.probe",
            allowed_connections=frozenset(), allowed_entities=frozenset(), catalogs=None,
        )
        MERGE_TARGET_CONTRIBUTION.run(None, ctx, result)

        assert result.issues == []


class TestItIsActuallyWiredIn:
    """The assertion whose absence let the lane-header fix half-land: every test above calls the
    contribution directly, so all of them stay green with it unregistered. A rule the module does not
    return is a rule the verifier never runs."""

    def test_the_activity_module_returns_it(self) -> None:
        from src.diagram_types.activity import module as activity_module

        codes = {
            code
            for contribution in activity_module.diagram_verification_contributions()
            for code in contribution.diagnostic_codes
        }

        assert "W047" in codes, "the activity module does not offer the merge-target rule"

    def test_it_reaches_a_diagram_through_the_verifier(self, tmp_path) -> None:
        """End to end, through the real verifier on a real file — the only shape that proves a reader
        would see it."""
        from pathlib import Path

        from src.application.verification.artifact_verifier import ArtifactVerifier
        from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs

        body = """---
artifact-id: ACT@1780000001.aaaaaa.probe
artifact-type: diagram
diagram-type: activity
name: Probe
version: 0.1.0
status: draft
last-updated: '2026-08-24'
diagram-entities:
  decision:
  - id: d_ops
    label: Ready?
  action:
  - id: s_merge
    label: Merge
  - id: s_contact
    label: Contact
connections:
- id: t1
  conn_type: step-then
  source: d_ops
  target: s_merge
- id: e1
  conn_type: step-else
  source: d_ops
  target: s_contact
- id: m1
  conn_type: step-flow
  source: d_ops
  target: s_merge
---
@startuml
title Probe
start
if ([[arch://d_ops Ready?]]) then (yes)
:[[arch://s_merge Merge]];
else (no)
:[[arch://s_contact Contact]];
endif
:[[arch://s_merge Merge]];
stop
@enduml
"""
        # A registry, because `run_diagram_contributions` is gated on one: without it the whole
        # registry-dependent branch is skipped and the diagram verifies with a "no registry" notice.
        # That gate is why calling the contribution directly proves nothing about the product.
        from src.application.verification.artifact_verifier import ArtifactRegistry
        from src.infrastructure.artifact_index import shared_artifact_index

        repo = Path(tmp_path) / "engagements" / "ENG-T" / "architecture-repository"
        diagram = repo / "diagram-catalog" / "diagrams" / "ACT@1780000001.aaaaaa.probe.puml"
        diagram.parent.mkdir(parents=True, exist_ok=True)
        (repo / "model").mkdir(parents=True, exist_ok=True)
        diagram.write_text(body, encoding="utf-8")

        index = shared_artifact_index(repo)
        index.refresh()
        verifier = ArtifactVerifier(
            ArtifactRegistry(index),
            check_puml_syntax=False,
            catalogs=build_runtime_catalogs(build_module_registry()),
        )

        result = verifier.verify_diagram_file(diagram)

        assert "W047" in [issue.code for issue in result.issues], [
            (issue.code, issue.message) for issue in result.issues
        ]
