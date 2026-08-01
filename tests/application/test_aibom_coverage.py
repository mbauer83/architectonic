"""WU-B3: AIBOM coverage evaluation — each gap class detected independently, a fully
specified component reporting clean."""

from __future__ import annotations

from src.application.aibom.coverage import evaluate_coverage
from src.application.aibom.derivation import AibomComponent, ProvenancedValue, RoleMatch
from src.domain.assurance.aibom_roles import role_bindings_from_mapping


def _component(**over) -> AibomComponent:
    base = dict(
        entity_id="APP@1.a.model", name="model", specialization="ai-model",
        component_type="machine-learning-model",
    )
    base.update(over)
    return AibomComponent(**base)


def _full_bindings():
    # Every vocabulary role bound → no repo-wide unbound-role finding.
    from pathlib import Path

    from src.ontologies.archimate_4._yaml_data import load_module_aibom_roles

    return load_module_aibom_roles(Path("src/ontologies/archimate_4"))


def _authored(*names: str):
    return {n: ProvenancedValue(value="x", provenance="authored") for n in names}


def _dataset():
    return RoleMatch(
        role="trained-on", target_entity_id="DOB@1.b.d", target_name="d", target_specialization="ai-dataset"
    )


def _governance():
    return RoleMatch(role="governed-by", target_entity_id="BRL@1.c.o", target_name="o", target_specialization="")


def test_fully_specified_component_is_clean() -> None:
    comp = _component(
        authored=_authored("Task", "Approach"), datasets=(_dataset(),), governance=(_governance(),)
    )
    cov = evaluate_coverage([comp], {"ai-model": ["Task", "Approach"]}, _full_bindings())
    assert cov.clean
    assert cov.components[0].clean


def test_missing_required_attribute_detected() -> None:
    comp = _component(authored=_authored("Task"), datasets=(_dataset(),), governance=(_governance(),))
    cov = evaluate_coverage([comp], {"ai-model": ["Task", "Approach"]}, _full_bindings())
    report = cov.components[0]
    assert report.missing_required_attributes == ("Approach",)
    assert not report.clean


def test_missing_dataset_linkage_detected_for_a_model() -> None:
    comp = _component(authored=_authored("Task"), datasets=(), governance=(_governance(),))
    cov = evaluate_coverage([comp], {"ai-model": ["Task"]}, _full_bindings())
    assert cov.components[0].missing_dataset_linkage is True


def test_missing_governance_detected() -> None:
    comp = _component(authored=_authored("Task"), datasets=(_dataset(),), governance=())
    cov = evaluate_coverage([comp], {"ai-model": ["Task"]}, _full_bindings())
    assert cov.components[0].missing_governance is True


def test_dataset_gap_not_raised_for_a_dataset_component() -> None:
    # A dataset does not itself need a dataset link; the gap class is scoped to models/agents.
    comp = _component(
        entity_id="DOB@1.b.d", name="d", specialization="ai-dataset", component_type="data",
        authored=_authored(),
    )
    cov = evaluate_coverage([comp], {}, _full_bindings())
    assert cov.components[0].missing_dataset_linkage is False
    assert cov.components[0].missing_governance is False  # datasets aren't in the governance-expected set


def test_recommended_missing_is_advisory_not_blocking() -> None:
    # "handle optional/unavailable sensibly": a missing recommended attribute is surfaced but
    # does NOT make the component unclean — only complete is false.
    comp = _component(authored=_authored("Task"), datasets=(_dataset(),), governance=(_governance(),))
    cov = evaluate_coverage(
        [comp], {"ai-model": ["Task"]}, _full_bindings(), recommended_attributes={"ai-model": ["Approach"]}
    )
    report = cov.components[0]
    assert report.missing_recommended_attributes == ("Approach",)
    assert report.clean is True  # valid despite the advisory gap
    assert report.complete is False


def test_unbound_role_is_a_repo_wide_finding() -> None:
    # Only trained-on bound → the other eight vocabulary roles are unbound findings.
    partial = role_bindings_from_mapping(
        {"roles": {"trained-on": {"connection_types": ["archimate-access"]}}}, label="test"
    )
    cov = evaluate_coverage([], {}, partial)
    assert "governed-by" in cov.unbound_roles
    assert "trained-on" not in cov.unbound_roles
    assert not cov.clean
