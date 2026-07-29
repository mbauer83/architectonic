"""WU-B1: the pure AIBOM derivation core. Each derivation role in isolation, the dependency
graph (including cycle termination), authored provenance, and the sparse no-relations
component — all with no store, HTTP, or IO."""

from __future__ import annotations

from pathlib import Path

from src.application.aibom_derivation import (
    AI_COMPONENT_TYPE,
    AI_SPECIALIZATIONS,
    ProvenancedValue,
    ai_specialization_of,
    derive_aibom,
)
from src.domain.assurance.aibom_roles import role_bindings_from_mapping
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord


def _entity(
    artifact_id: str, artifact_type: str, *, specialization: str = "", attributes: dict | None = None
) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id, artifact_type=artifact_type, name=artifact_id.split(".")[-1],
        version="0.1.0", status="draft", domain="application", subdomain="", path=Path(f"/{artifact_id}.md"),
        keywords=(), extra={}, content_text="", display_blocks={}, display_label="", display_alias="",
        specialization=specialization, attributes=attributes or {},
    )


def _conn(source: str, target: str, conn_type: str) -> ConnectionRecord:
    return ConnectionRecord(
        artifact_id=f"{source}---{target}@@{conn_type}", source=source, target=target,
        conn_type=conn_type, version="0.1.0", status="draft", path=Path("/c.outgoing.md"), extra={}, content_text="",
    )


def _bindings():
    return role_bindings_from_mapping(
        {
            "roles": {
                "trained-on": {"connection_types": ["archimate-access"], "target_specializations": ["ai-dataset"]},
                "governed-by": {"connection_types": ["archimate-assignment"], "target_specializations": []},
            }
        },
        label="test",
    )


def test_drift_guard_every_shipped_ai_specialization_has_a_component_type() -> None:
    # The AIBOM component-type map must stay in step with the ontology's AI specializations.
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs

    c = build_runtime_catalogs(build_module_registry())
    shipped = {
        s.slug
        for base in ("application-component", "service", "data-object", "system-software", "application-interface")
        for s in c.specializations.for_type("entity", base)
        if s.slug.startswith("ai-")
    }
    assert shipped == AI_SPECIALIZATIONS, f"drift: ontology {shipped} vs map {set(AI_COMPONENT_TYPE)}"


def test_only_ai_entities_become_components() -> None:
    entities = [
        _entity("APP@1.a.model", "application-component", specialization="ai-model"),
        _entity("APP@1.b.plain", "application-component"),  # no AI specialization
    ]
    comps = derive_aibom(entities, [], _bindings())
    assert [c.entity_id for c in comps] == ["APP@1.a.model"]
    assert comps[0].component_type == "machine-learning-model"


def test_trained_on_dataset_role_resolves() -> None:
    model = _entity("APP@1.a.model", "application-component", specialization="ai-model")
    dataset = _entity("DOB@1.b.data", "data-object", specialization="ai-dataset")
    conns = [_conn(model.artifact_id, dataset.artifact_id, "archimate-access")]
    comps = derive_aibom([model, dataset], conns, _bindings())
    model_comp = next(c for c in comps if c.specialization == "ai-model")
    assert [d.target_entity_id for d in model_comp.datasets] == [dataset.artifact_id]
    assert model_comp.datasets[0].role == "trained-on"


def test_role_does_not_match_wrong_target_specialization() -> None:
    model = _entity("APP@1.a.model", "application-component", specialization="ai-model")
    prompt = _entity("DOB@1.c.prompt", "data-object", specialization="ai-prompt-asset")
    conns = [_conn(model.artifact_id, prompt.artifact_id, "archimate-access")]
    comps = derive_aibom([model, prompt], conns, _bindings())
    model_comp = next(c for c in comps if c.specialization == "ai-model")
    assert model_comp.datasets == ()  # a prompt asset is not a dataset


def test_governance_role_resolves() -> None:
    model = _entity("APP@1.a.model", "application-component", specialization="ai-model")
    owner = _entity("BRL@1.d.owner", "role")  # a plain accountable role
    conns = [_conn(model.artifact_id, owner.artifact_id, "archimate-assignment")]
    comps = derive_aibom([model, owner], conns, _bindings())
    model_comp = next(c for c in comps if c.specialization == "ai-model")
    assert [g.target_entity_id for g in model_comp.governance] == [owner.artifact_id]


def test_dependency_graph_between_ai_components() -> None:
    agent = _entity("APP@1.a.agent", "application-component", specialization="ai-agent")
    model = _entity("APP@1.b.model", "application-component", specialization="ai-model")
    conns = [_conn(agent.artifact_id, model.artifact_id, "archimate-serving")]
    comps = derive_aibom([agent, model], conns, _bindings())
    agent_comp = next(c for c in comps if c.specialization == "ai-agent")
    assert agent_comp.dependency_ids == (model.artifact_id,)


def test_dependency_cycle_terminates() -> None:
    a = _entity("APP@1.a.a", "application-component", specialization="ai-agent")
    b = _entity("APP@1.b.b", "application-component", specialization="ai-model")
    conns = [_conn(a.artifact_id, b.artifact_id, "archimate-serving"),
             _conn(b.artifact_id, a.artifact_id, "archimate-serving")]
    comps = derive_aibom([a, b], conns, _bindings())  # must not loop
    deps = {c.specialization: c.dependency_ids for c in comps}
    assert deps["ai-agent"] == (b.artifact_id,)
    assert deps["ai-model"] == (a.artifact_id,)


def test_authored_attributes_are_carried_with_authored_provenance() -> None:
    model = _entity(
        "APP@1.a.model", "application-component", specialization="ai-model",
        attributes={"Task": "classification", "Supplier": "ACME", "Inputs": ""},
    )
    comps = derive_aibom([model], [], _bindings())
    authored = comps[0].authored
    assert authored["Task"] == ProvenancedValue(value="classification", provenance="authored")
    assert authored["Supplier"].provenance == "authored"
    assert "Inputs" not in authored  # empty values are dropped


def test_entity_with_no_relations_is_a_valid_sparse_component() -> None:
    model = _entity("APP@1.a.model", "application-component", specialization="ai-model")
    comps = derive_aibom([model], [], _bindings())
    c = comps[0]
    assert c.datasets == () and c.governance == () and c.dependency_ids == () and c.authored == {}
    assert c.component_type == "machine-learning-model"  # still typed and valid


def test_considerations_reach_stakeholders_and_drivers_within_depth() -> None:
    # WU-B2: users ← stakeholders, useCases ← drivers/goals, bounded by depth.
    model = _entity("APP@1.a.model", "application-component", specialization="ai-model")
    stakeholder = _entity("STK@1.b.user", "stakeholder")
    driver = _entity("DRV@1.c.why", "driver")
    conns = [
        _conn(model.artifact_id, stakeholder.artifact_id, "archimate-association"),
        _conn(model.artifact_id, driver.artifact_id, "archimate-influence"),
    ]
    comps = derive_aibom([model, stakeholder, driver], conns, _bindings(), consideration_depth=2)
    c = comps[0]
    assert [u.entity_id for u in c.considerations.users] == [stakeholder.artifact_id]
    assert [u.entity_id for u in c.considerations.use_cases] == [driver.artifact_id]


def test_considerations_depth_bound_is_honoured() -> None:
    # A driver two hops away is unreachable at depth 1.
    model = _entity("APP@1.a.model", "application-component", specialization="ai-model")
    mid = _entity("APP@1.m.mid", "application-component")
    driver = _entity("DRV@1.c.why", "driver")
    conns = [
        _conn(model.artifact_id, mid.artifact_id, "archimate-serving"),
        _conn(mid.artifact_id, driver.artifact_id, "archimate-influence"),
    ]
    depth1 = derive_aibom([model, mid, driver], conns, _bindings(), consideration_depth=1)[0]
    assert depth1.considerations.use_cases == ()
    depth2 = derive_aibom([model, mid, driver], conns, _bindings(), consideration_depth=2)[0]
    assert [u.entity_id for u in depth2.considerations.use_cases] == [driver.artifact_id]


def test_unreachable_motivation_yields_empty_not_error() -> None:
    model = _entity("APP@1.a.model", "application-component", specialization="ai-model")
    comps = derive_aibom([model], [], _bindings())
    assert comps[0].considerations.users == () and comps[0].considerations.use_cases == ()


def test_ai_specialization_of_reads_the_first_ai_slug() -> None:
    e = _entity("APP@1.a.x", "application-component")
    object.__setattr__(e, "specializations", ("module", "ai-model"))
    assert ai_specialization_of(e) == "ai-model"
