"""What is offered when occurrence is asked for — and what is never offered.

The one rule that matters more than the rest: the value is never suggested. Occurrence is a claim
about frequency, nothing in the model measures one, and a pre-filled value would carry the
appearance of derivation with none of the substance. What the model contributes is citations.

The second rule: vulnerability findings are a *narrow* input. They appear only for a security
concern class with an SBOM anchored, because for a safety or operational failure mode they say
nothing — and a surface that led with them would mis-frame the method.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.assurance.fmea_occurrence_evidence import OccurrenceEvidence, occurrence_evidence
from src.domain.assurance.fmea_structural_signals import TypedEdge


@dataclass(frozen=True)
class _TypeInfo:
    derivation_role: str | None
    derivation_strength: int | None


_CATALOG: dict[str, Any] = {
    "archimate-serving": _TypeInfo("dependency", 4),
    "archimate-access": _TypeInfo("dependency", 3),
}


def _edge(source: str, connection_type: str, target: str) -> TypedEdge:
    info = _CATALOG[connection_type]
    return TypedEdge(
        connection_id=f"{source}-{connection_type}-{target}",
        source_id=source, target_id=target, connection_type=connection_type,
        role=info.derivation_role, strength=info.derivation_strength,
    )


def _kinds(evidence: OccurrenceEvidence) -> list[str]:
    return [fact.kind for fact in evidence.facts]


class TestTheValueIsNeverSuggested:
    def test_the_evidence_carries_no_value_field(self) -> None:
        """Structural: the surface has nothing to pre-fill the field with, even by accident."""
        evidence = occurrence_evidence("APP@1", concern_class="safety", edges=[])

        assert not {"value", "suggested_value", "occurrence", "estimate"} & set(vars(evidence))

    def test_the_rationale_draft_contains_no_scale_member(self) -> None:
        from src.domain.assurance.fmea_factors import OCCURRENCE_SCALE

        edges = [_edge("APP@2", "archimate-serving", "APP@1")]
        draft = occurrence_evidence("APP@1", concern_class="safety", edges=edges).rationale_draft()

        assert not [member for member in OCCURRENCE_SCALE if member in draft]


class TestStructuralFactsAreCited:
    def test_dependents_are_reported_with_their_witness(self) -> None:
        edges = [_edge("APP@2", "archimate-serving", "APP@1")]

        evidence = occurrence_evidence("APP@1", concern_class="safety", edges=edges)

        assert "dependents" in _kinds(evidence)
        assert evidence.facts[0].witness

    def test_being_a_sole_provider_is_called_out(self) -> None:
        edges = [_edge("APP@client", "archimate-serving", "APP@store")]

        evidence = occurrence_evidence("APP@store", concern_class="safety", edges=edges)

        assert "sole-provider" in _kinds(evidence)

    def test_a_shared_dependency_under_a_redundant_pair_is_called_out(self) -> None:
        edges = [
            _edge("APP@client", "archimate-serving", "APP@primary"),
            _edge("APP@client", "archimate-serving", "APP@standby"),
            _edge("APP@primary", "archimate-access", "APP@store"),
            _edge("APP@standby", "archimate-access", "APP@store"),
        ]

        evidence = occurrence_evidence("APP@primary", concern_class="safety", edges=edges)

        assert "common-cause" in _kinds(evidence)
        assert any("APP@store" in fact.text for fact in evidence.facts)

    def test_an_unmodelled_element_says_so_rather_than_reporting_zero(self) -> None:
        evidence = occurrence_evidence("APP@lonely", concern_class="safety", edges=[])

        assert "structure" in _kinds(evidence)
        assert "no modelled relationships" in evidence.facts[0].text

    def test_a_thin_neighbourhood_is_flagged_in_the_citation(self) -> None:
        edges = [_edge("APP@2", "archimate-serving", "APP@1")]

        evidence = occurrence_evidence("APP@1", concern_class="safety", edges=edges)

        assert "thinly modelled" in evidence.facts[0].text


class TestDataClassificationIsReadThroughTheGraph:
    def test_the_classification_of_accessed_data_is_cited(self) -> None:
        """The component declares nothing: the classification lives on the data."""
        connections = [{
            "artifact_id": "CON@1", "source": "APP@1", "target": "DAT@1",
            "connection_type": "archimate-access",
        }]
        entities = {"DAT@1": {"artifact_type": "data-object", "Sensitivity": "Strictly Confidential"}}

        evidence = occurrence_evidence(
            "APP@1", concern_class="safety", edges=[], connections=connections, entities=entities,
        )

        assert "data-sensitivity" in _kinds(evidence)
        assert any("Strictly Confidential" in fact.text for fact in evidence.facts)

    def test_unclassified_data_contributes_nothing(self) -> None:
        connections = [{
            "artifact_id": "CON@1", "source": "APP@1", "target": "DAT@1",
            "connection_type": "archimate-access",
        }]
        entities: dict[str, dict[str, object]] = {"DAT@1": {"artifact_type": "data-object"}}

        evidence = occurrence_evidence(
            "APP@1", concern_class="safety", edges=[], connections=connections, entities=entities,
        )

        assert "data-sensitivity" not in _kinds(evidence)

    def test_data_another_component_accesses_is_not_cited_here(self) -> None:
        connections = [{
            "artifact_id": "CON@1", "source": "APP@other", "target": "DAT@1",
            "connection_type": "archimate-access",
        }]
        entities = {"DAT@1": {"artifact_type": "data-object", "Sensitivity": "Confidential"}}

        evidence = occurrence_evidence(
            "APP@1", concern_class="safety", edges=[], connections=connections, entities=entities,
        )

        assert "data-sensitivity" not in _kinds(evidence)


class TestVulnerabilitiesAreANarrowInput:
    def test_they_appear_for_a_security_concern_with_an_sbom(self) -> None:
        evidence = occurrence_evidence(
            "APP@1", concern_class="security", edges=[],
            vulnerability_ids=["VID@1"], sbom_anchored=True,
        )

        assert "vulnerabilities" in _kinds(evidence)

    def test_they_never_appear_for_a_safety_concern(self) -> None:
        """They say nothing about whether a component fails to perform its function."""
        evidence = occurrence_evidence(
            "APP@1", concern_class="safety", edges=[],
            vulnerability_ids=["VID@1"], sbom_anchored=True,
        )

        assert "vulnerabilities" not in _kinds(evidence)

    def test_they_never_appear_without_an_sbom_anchored(self) -> None:
        evidence = occurrence_evidence(
            "APP@1", concern_class="security", edges=[],
            vulnerability_ids=["VID@1"], sbom_anchored=False,
        )

        assert "vulnerabilities" not in _kinds(evidence)

    def test_everything_else_still_works_with_no_sbom_anywhere(self) -> None:
        """The whole surface has to be usable in a safety analysis that has never seen an SBOM."""
        edges = [_edge("APP@2", "archimate-serving", "APP@1")]

        evidence = occurrence_evidence("APP@1", concern_class="safety", edges=edges)

        assert "dependents" in _kinds(evidence)
        assert evidence.rationale_draft()

    def test_the_security_snapshot_enters_the_basis_only_for_security(self) -> None:
        """So a new disclosure retires a security judgement and leaves safety judgements alone."""
        secure = occurrence_evidence(
            "APP@1", concern_class="security", edges=[], vulnerability_ids=["VID@1"],
            sbom_anchored=True, security_basis_snapshot_id="SNP@1",
        )
        safe = occurrence_evidence(
            "APP@1", concern_class="safety", edges=[], vulnerability_ids=["VID@1"],
            sbom_anchored=True, security_basis_snapshot_id="SNP@1",
        )

        assert any("SNP@1" in item for item in secure.basis)
        assert not any("SNP@1" in item for item in safe.basis)


class TestTheBasisTracksWhatWasCited:
    def test_the_basis_is_stable_for_an_unchanged_model(self) -> None:
        edges = [_edge("APP@2", "archimate-serving", "APP@1")]

        first = occurrence_evidence("APP@1", concern_class="safety", edges=edges).basis
        second = occurrence_evidence("APP@1", concern_class="safety", edges=edges).basis

        assert first == second

    def test_a_new_dependent_moves_the_basis(self) -> None:
        """Which is what retires an occurrence judgement that cited the old picture."""
        before = occurrence_evidence(
            "APP@1", concern_class="safety", edges=[_edge("APP@2", "archimate-serving", "APP@1")],
        ).basis
        after = occurrence_evidence(
            "APP@1", concern_class="safety",
            edges=[
                _edge("APP@2", "archimate-serving", "APP@1"),
                _edge("APP@3", "archimate-serving", "APP@1"),
            ],
        ).basis

        assert before != after
