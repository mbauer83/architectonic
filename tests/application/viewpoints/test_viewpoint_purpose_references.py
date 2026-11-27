"""A viewpoint definition's purpose-line references are checked against the repository on persist, by the same
check a diagram's lines go through: a missing element and an element of a type its list does not admit are
refused; prose is never looked up.

Against fixtures this file builds, so exact contents are the test's own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.application.verification._verifier_rules_purpose_lines import check_purpose_lines
from src.application.verification.artifact_verifier_types import VerificationResult
from src.application.verification.purpose_line_references import PurposeLineResolution
from src.application.viewpoints.persist_definition import persist_viewpoint_definition
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.purpose_lines import Prose, PurposeLines, Reference, purpose_lines_as_written
from src.domain.viewpoints.viewpoints import ViewpointCatalog, ViewpointDefinition
from tests.application.viewpoints._fixtures import PURPOSE_LINE_TYPES, REGISTRIES, EntityTable, entity

STAKEHOLDER = entity(artifact_id="STK@1.aa.ops", artifact_type="stakeholder", name="Operations")
GOAL = entity(artifact_id="GOL@1.bb.fast", artifact_type="goal", name="Fast")
COMPONENT = entity(artifact_id="APP@1.cc.shop", artifact_type="application-component", name="Shop")
MISSING_ID = "STK@1.zz.gone"


@dataclass
class _AskedTable:
    """An entity table that records every id it is asked about."""

    table: EntityTable
    asked: list[str] = field(default_factory=list)

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        self.asked.append(artifact_id)
        return self.table.get_entity(artifact_id)


def _resolution(entities: _AskedTable | EntityTable | None = None) -> PurposeLineResolution:
    return PurposeLineResolution(entities or EntityTable((STAKEHOLDER, GOAL, COMPONENT)), PURPOSE_LINE_TYPES)


def _create(lines: PurposeLines, resolution: PurposeLineResolution):
    definition = ViewpointDefinition(
        slug="purposeful", version=1, name="Purposeful", stakeholders=lines.stakeholders, concerns=lines.concerns
    )
    return persist_viewpoint_definition(
        "create",
        definition,
        local_catalog=ViewpointCatalog.empty(),
        merged_catalog=ViewpointCatalog.empty(),
        registries=REGISTRIES,
        purpose_references=resolution,
    )


def test_a_reference_to_an_element_the_repository_does_not_hold_is_refused() -> None:
    lines = PurposeLines(stakeholders=(Prose("Warehouse"), Reference(MISSING_ID)))

    result = _create(lines, _resolution())

    assert result.ok is False and result.catalog_to_write is None
    [issue] = result.issues
    assert (issue.severity, issue.code, issue.path) == ("error", "unknown-purpose-reference", "/stakeholders/1")
    assert MISSING_ID in issue.message and issue.found == MISSING_ID


def test_a_reference_to_an_element_its_list_does_not_admit_is_refused() -> None:
    lines = PurposeLines(
        stakeholders=(Reference(STAKEHOLDER.artifact_id),), concerns=(Reference(COMPONENT.artifact_id),)
    )

    result = _create(lines, _resolution())

    assert result.ok is False
    [issue] = result.issues
    assert (issue.severity, issue.code, issue.path) == ("error", "purpose-reference-type-mismatch", "/concerns/0")
    assert issue.found == "application-component"
    assert issue.expected == "goal, stakeholder"


def test_a_goal_cannot_stand_as_a_stakeholder() -> None:
    result = _create(PurposeLines(stakeholders=(Reference(GOAL.artifact_id),)), _resolution())

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("purpose-reference-type-mismatch", "/stakeholders/0")
    ]


def test_resolving_references_are_kept_and_prose_is_never_looked_up() -> None:
    asked = _AskedTable(EntityTable((STAKEHOLDER, GOAL)))
    lines = PurposeLines(
        stakeholders=(Prose("Operations team"), Reference(STAKEHOLDER.artifact_id)),
        concerns=(Prose("How does an order reach the warehouse?"), Reference(GOAL.artifact_id)),
    )

    result = _create(lines, _resolution(asked))

    assert result.ok is True and result.issues == ()
    assert asked.asked == [STAKEHOLDER.artifact_id, GOAL.artifact_id]
    stored = result.catalog_to_write.get("purposeful") if result.catalog_to_write else None
    assert stored is not None and stored.purpose_lines == lines


def test_a_viewpoint_and_a_diagram_report_the_same_fault_in_the_same_words() -> None:
    """One check: the diagram verifier's E186/E187 and the viewpoint's issues spell the same findings."""
    lines = PurposeLines(stakeholders=(Reference(MISSING_ID),), concerns=(Reference(COMPONENT.artifact_id),))
    diagram = VerificationResult(path=Path("diagram.puml"), file_type="diagram")

    check_purpose_lines(purpose_lines_as_written(lines), _resolution(), diagram, "diagram.puml")
    viewpoint = _create(lines, _resolution())

    assert [issue.code for issue in diagram.issues] == ["E186", "E187"]
    assert [issue.message for issue in diagram.issues] == [issue.message for issue in viewpoint.issues]
