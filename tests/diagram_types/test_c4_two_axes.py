"""The two C4 axes the module gained: the portfolio above, and the placement beside.

`_C4_LEVELS` used to be a linear depth with a comment saying why a landscape had no row in it. It
has one now, and deployment deliberately does not — a deployment view draws the *same* containers a
container view draws, placed on the technology that hosts them, so calling it level 4 would tell a
reader it sits below components.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.diagram_types.c4._c4_types import _ResolvedItem, _ResolvedState
from src.diagram_types.c4._navigation import build_c4_navigation
from src.diagram_types.c4._projection import project_c4_landscape, project_c4_scope
from src.diagram_types.c4._projection_deployment import project_c4_deployment
from src.diagram_types.c4._projection_vocabulary import is_externally_styled
from src.diagram_types.c4._resolve_model import _declared_technology
from src.diagram_types.c4._resolve_nesting import _nest
from src.diagram_types.c4.renderer import C4PumlRenderer
from tests.application.derivation._fixtures import FakeQuery, _connection, _entity

_PERSON_TYPES: frozenset[str] = frozenset({"business-actor", "role"})


def _roles(projection: Any) -> dict[str, str]:
    return {item.entity_id: item.role for item in projection.items}


# ---------------------------------------------------------------------------
# The landscape: a scope that is a set
# ---------------------------------------------------------------------------


def _portfolio() -> FakeQuery:
    """Two systems, one shared third party, and one container inside the first."""
    return FakeQuery(
        entities=[
            _entity("BILLING"),
            _entity("CRM"),
            _entity("BILLING_API"),
            _entity("PAYMENTS_SAAS"),
            _entity("CLERK", "business-actor"),
        ],
        connections=[
            _connection("c-billing-api", "BILLING", "BILLING_API", "archimate-composition"),
            _connection("c-api-saas", "BILLING_API", "PAYMENTS_SAAS", "archimate-serving"),
            _connection("c-clerk-crm", "CLERK", "CRM", "archimate-association"),
            _connection("c-billing-crm", "BILLING", "CRM", "archimate-serving"),
        ],
    )


def test_every_scoped_system_is_a_scope_item() -> None:
    projection = project_c4_landscape(
        ("BILLING", "CRM"), _portfolio(),
        scope_entity_type="software-system", person_archimate_types=_PERSON_TYPES,
    )

    assert _roles(projection)["BILLING"] == "scope"
    assert _roles(projection)["CRM"] == "scope"


def test_a_scoped_system_is_never_drawn_as_an_external_peer() -> None:
    """The distinction this level makes is ours-versus-theirs, and a system in the portfolio is
    ours however it is reached — including from another portfolio member."""
    projection = project_c4_landscape(
        ("BILLING", "CRM"), _portfolio(),
        scope_entity_type="software-system", person_archimate_types=_PERSON_TYPES,
    )

    assert [item.entity_id for item in projection.items if item.role == "external"] == [
        "CLERK", "PAYMENTS_SAAS",
    ]


def test_a_descendant_rolls_up_to_the_system_that_holds_it() -> None:
    """`scope_of` is what lets a landscape draw a descendant's outside edge on its own system's
    box; the rule it replaced could only ever name one root."""
    projection = project_c4_landscape(
        ("BILLING", "CRM"), _portfolio(),
        scope_entity_type="software-system", person_archimate_types=_PERSON_TYPES,
    )

    assert dict(projection.scope_of)["BILLING_API"] == "BILLING"


def test_a_landscape_references_the_systems_it_scopes() -> None:
    projection = project_c4_landscape(
        ("BILLING", "CRM"), _portfolio(),
        scope_entity_type="software-system", person_archimate_types=_PERSON_TYPES,
    )

    assert {"BILLING", "CRM"} <= projection.to_candidate_set().entity_ids


def test_a_landscape_naming_one_system_does_not_fall_through_to_the_single_root_algorithm() -> None:
    """The dispatcher keys off the type, not the count: the single-root table has no landscape row,
    so a one-system landscape would otherwise project to nothing at all."""
    projection = project_c4_scope(
        "c4-system-landscape", ("BILLING",), _portfolio(),
        internal_c4_type="container", scope_entity_type="software-system",
        person_archimate_types=_PERSON_TYPES,
    )

    assert _roles(projection)["BILLING"] == "scope"


# ---------------------------------------------------------------------------
# Deployment: the second axis
# ---------------------------------------------------------------------------


def _deployed() -> FakeQuery:
    """A system with two containers, one of them deployed onto a node via its artifact."""
    return FakeQuery(
        entities=[
            _entity("BILLING"),
            _entity("API"),
            _entity("UNDEPLOYED"),
            _entity("API_IMAGE", "artifact"),
            _entity("CLUSTER", "technology-node"),
        ],
        connections=[
            _connection("c-b-api", "BILLING", "API", "archimate-composition"),
            _connection("c-b-und", "BILLING", "UNDEPLOYED", "archimate-composition"),
            _connection("c-img-api", "API_IMAGE", "API", "archimate-realization"),
            _connection("c-cluster-img", "CLUSTER", "API_IMAGE", "archimate-aggregation"),
        ],
    )


def _deployment_projection() -> Any:
    return project_c4_deployment(
        "BILLING", _deployed(),
        internal_c4_type="container", scope_entity_type="software-system",
        person_archimate_types=_PERSON_TYPES,
    )


def test_the_host_is_reached_through_the_artifact_that_realizes_the_container() -> None:
    """ArchiMate has no host→application-component relation and `connections.yaml` permits none;
    the deployment fact is `host -assignment-> artifact -realization-> component`. Aggregation from
    a technology node is read on the first hop as well, because it was the only path the table
    offered before 0.7.1 — which is what this fixture draws."""
    projection = _deployment_projection()

    assert _roles(projection)["CLUSTER"] == "internal"
    assert dict(projection.contained_by)["API"] == "CLUSTER"


def test_a_container_with_no_artifact_is_left_out_rather_than_given_a_host() -> None:
    projection = _deployment_projection()

    assert "UNDEPLOYED" not in _roles(projection)


def _deployed_on_system_software(hosting: str) -> FakeQuery:
    """The shape defect 12 was reported as: the only host is system software, not a node.

    Four of the five declared host types could not hold an artifact at all, so a model that said
    where its containers run in the obvious way projected an empty view.
    """
    return FakeQuery(
        entities=[
            _entity("BILLING"), _entity("API"),
            _entity("API_IMAGE", "artifact"),
            _entity("RUNTIME", "system-software"),
        ],
        connections=[
            _connection("c-b-api", "BILLING", "API", "archimate-composition"),
            _connection("c-img-api", "API_IMAGE", "API", "archimate-realization"),
            _connection("c-rt-img", "RUNTIME", "API_IMAGE", hosting),
        ],
    )


@pytest.mark.parametrize("hosting", ["archimate-assignment", "archimate-aggregation"])
def test_a_host_that_is_not_a_node_still_holds_its_container(hosting: str) -> None:
    """Both relations: assignment is what a deployment should now say, aggregation is what models
    authored against the only previously permitted path already say."""
    projection = project_c4_deployment(
        "BILLING", _deployed_on_system_software(hosting),
        internal_c4_type="container", scope_entity_type="software-system",
        person_archimate_types=_PERSON_TYPES,
    )

    assert _roles(projection)["RUNTIME"] == "internal"
    assert dict(projection.contained_by)["API"] == "RUNTIME"


def test_a_host_inside_a_node_keeps_its_enclosing_node() -> None:
    """The shape of the shipped self-model, and the regression that pins two sets rather than one.

    `node --composition--> host --aggregation--> artifact --realization--> component`. Composition
    between hosts is permitted and the self-model states six of them; composition into an *artifact*
    is permitted from no host at all. A single shrunken set of hosting types — which was the first
    answer to this defect — would read the containment away and draw the whole deployment as one
    flat box, which says the containers run side by side on a machine rather than together inside a
    runtime.
    """
    query = FakeQuery(
        entities=[
            _entity("BILLING"), _entity("API"),
            _entity("API_IMAGE", "artifact"),
            _entity("RUNTIME", "system-software"),
            _entity("MACHINE", "technology-node"),
        ],
        connections=[
            _connection("c-b-api", "BILLING", "API", "archimate-composition"),
            _connection("c-img-api", "API_IMAGE", "API", "archimate-realization"),
            _connection("c-rt-img", "RUNTIME", "API_IMAGE", "archimate-aggregation"),
            _connection("c-m-rt", "MACHINE", "RUNTIME", "archimate-composition"),
        ],
    )

    projection = project_c4_deployment(
        "BILLING", query, internal_c4_type="container", scope_entity_type="software-system",
        person_archimate_types=_PERSON_TYPES,
    )

    contained = dict(projection.contained_by)
    assert contained["API"] == "RUNTIME"
    assert contained["RUNTIME"] == "MACHINE", "the enclosing node was flattened away"


def test_the_deployed_system_is_the_title_rather_than_a_drawn_box() -> None:
    """`scope_render_mode: deployment` draws the hosts, not the system — so the scope entity is not
    part of what the diagram references, exactly as at container and component level."""
    projection = _deployment_projection()

    assert "BILLING" not in projection.to_candidate_set().entity_ids


# ---------------------------------------------------------------------------
# Navigation across the two axes
# ---------------------------------------------------------------------------


@dataclass
class FakeDiagramRecord:
    artifact_id: str
    diagram_type: str
    name: str
    extra: dict[str, Any]


def _repo(diagrams: list[FakeDiagramRecord]) -> MagicMock:
    repo = MagicMock()
    repo.list_diagrams = lambda: diagrams
    repo.get_entity = lambda _eid: None
    return repo


def _scoped(artifact_id: str, diagram_type: str, *scope_ids: str) -> FakeDiagramRecord:
    key = "_scope_entity_id" if len(scope_ids) == 1 else "_scope_entity_ids"
    value: Any = scope_ids[0] if len(scope_ids) == 1 else list(scope_ids)
    return FakeDiagramRecord(
        artifact_id=artifact_id,
        diagram_type=diagram_type,
        name=artifact_id,
        extra={"diagram-entities": {key: value}},
    )


def test_a_landscape_drills_down_into_the_context_of_each_system_it_holds() -> None:
    context = _scoped("CTX@1", "c4-system-context", "BILLING")
    navigation = build_c4_navigation(
        _repo([context]), "LS@1", "c4-system-landscape",
        {"_scope_entity_ids": ["BILLING", "CRM"]},
    )

    assert navigation is not None
    assert navigation["current_level"] == 0
    assert navigation["child_diagrams"] == [
        {
            "diagram_id": "CTX@1",
            "diagram_name": "CTX@1",
            "diagram_type": "c4-system-context",
            "scope_entity_id": "BILLING",
        }
    ]


def test_a_system_context_names_the_landscape_that_holds_it_as_a_parent() -> None:
    landscape = _scoped("LS@1", "c4-system-landscape", "BILLING", "CRM")
    navigation = build_c4_navigation(
        _repo([landscape]), "CTX@1", "c4-system-context", {"_scope_entity_id": "BILLING"}
    )

    assert navigation is not None
    assert [p["diagram_id"] for p in navigation["parent_diagrams"]] == ["LS@1"]


def test_a_deployment_view_is_neither_a_parent_nor_a_child_of_the_container_view() -> None:
    """The whole reason deployment is not a level: it would have to claim a place on an axis it
    does not sit on."""
    deployment = _scoped("DEP@1", "c4-deployment", "BILLING")
    navigation = build_c4_navigation(
        _repo([deployment]), "CNT@1", "c4-container", {"_scope_entity_id": "BILLING"}
    )

    assert navigation is not None
    assert navigation["parent_diagrams"] == []
    assert navigation["child_diagrams"] == []
    assert [d["diagram_id"] for d in navigation["deployment_diagrams"]] == ["DEP@1"]


def test_a_deployment_view_names_the_logical_views_of_the_same_system() -> None:
    container = _scoped("CNT@1", "c4-container", "BILLING")
    navigation = build_c4_navigation(
        _repo([container]), "DEP@1", "c4-deployment", {"_scope_entity_id": "BILLING"}
    )

    assert navigation is not None
    assert navigation["current_level"] is None
    assert [d["diagram_id"] for d in navigation["subject_diagrams"]] == ["CNT@1"]
    assert navigation["deployment_diagrams"] == []


def test_a_deployment_view_of_another_system_is_not_offered() -> None:
    other = _scoped("DEP@2", "c4-deployment", "CRM")
    navigation = build_c4_navigation(
        _repo([other]), "CNT@1", "c4-container", {"_scope_entity_id": "BILLING"}
    )

    assert navigation is not None
    assert navigation["deployment_diagrams"] == []


# ---------------------------------------------------------------------------
# What each axis renders
# ---------------------------------------------------------------------------


def _item(local_id: str, item_type: str, label: str, **kwargs: Any) -> _ResolvedItem:
    return _ResolvedItem(
        local_id=local_id, item_type=item_type, alias=local_id.upper(),
        label=label, description="", technology=kwargs.pop("technology", ""),
        external=kwargs.pop("external", False), **kwargs,
    )


def _render(config: dict[str, Any], state: _ResolvedState) -> str:
    renderer = C4PumlRenderer(config)
    with patch("src.diagram_types.c4.renderer.resolve_c4_state", return_value=state):
        return renderer.render_body("Two Axes", [], [], "c4-x", Path("/repo"), diagram_entities={})


def test_a_landscape_draws_every_system_in_its_scope() -> None:
    body = _render(
        {"c4": {"scope_entity_type": "software-system", "scope_render_mode": "node"}},
        _ResolvedState(
            scope_items=(
                _item("billing", "software-system", "Billing"),
                _item("crm", "software-system", "CRM"),
            ),
            scope_render_mode="node",
            outside_items=[_item("saas", "software-system", "Payments SaaS", external=True)],
        ),
    )

    assert 'System(BILLING, "Billing")' in body
    assert 'System(CRM, "CRM")' in body
    assert 'System_Ext(SAAS, "Payments SaaS")' in body


def test_a_deployment_view_nests_each_container_in_the_node_that_hosts_it() -> None:
    body = _render(
        {"c4": {
            "scope_entity_type": "software-system",
            "scope_render_mode": "deployment",
            "puml_stdlib": "C4_Deployment",
        }},
        _ResolvedState(
            scope_items=(_item("billing", "software-system", "Billing"),),
            scope_render_mode="deployment",
            internal_items=[
                _item(
                    "cluster", "node", "Kubernetes Cluster", technology="EKS",
                    children=(_item("api", "container", "API", technology="Python"),),
                )
            ],
        ),
    )

    assert "!include <C4/C4_Deployment>" in body
    assert 'Deployment_Node(CLUSTER, "Kubernetes Cluster", "EKS") {' in body
    assert '  Container(API, "API", "Python")' in body
    # The system in scope is the title, not a box: a `System(` call would say it is drawn.
    assert 'System(BILLING' not in body


def test_the_component_header_is_still_the_default() -> None:
    body = _render(
        {"c4": {"scope_entity_type": "software-system", "scope_render_mode": "node"}},
        _ResolvedState(
            scope_items=(_item("billing", "software-system", "Billing"),),
            scope_render_mode="node",
        ),
    )

    assert "!include <C4/C4_Component>" in body


# ---------------------------------------------------------------------------
# What "external" means
# ---------------------------------------------------------------------------


def test_a_person_is_never_drawn_external_in_a_model_backed_view() -> None:
    """The model has no way to say an actor is a foreigner: `external` is a property of a
    *standalone* diagram item, and ArchiMate's `external-active-structure-element` means an
    interface. Deriving it from role drew every actor in grey, including the architects the system
    is built for."""
    assert not is_externally_styled("external", "person")


def test_a_system_outside_the_scope_is_drawn_external() -> None:
    """For a system the two do coincide: the scope set is the model's own statement of what is
    being documented, so a system outside it is somebody else's."""
    assert is_externally_styled("external", "software-system")


def test_nothing_in_scope_or_inside_it_is_external() -> None:
    assert not is_externally_styled("scope", "software-system")
    assert not is_externally_styled("internal", "container")


# ---------------------------------------------------------------------------
# The technology line
# ---------------------------------------------------------------------------


class _Attributed:
    def __init__(self, **attributes: object) -> None:
        self.attributes = attributes


_TECH_ATTRS = ("Programming Languages & Versions", "Frameworks & Versions")


def test_the_language_and_the_first_framework_make_the_line() -> None:
    """C4's third macro argument is one short phrase, and this is the phrase C4 itself uses."""
    entity = _Attributed(**{
        "Programming Languages & Versions": '["Python >=3.13"]',
        "Frameworks & Versions": '["FastAPI >=0.115.0","Uvicorn >=0.32.0 (standard)","Pydantic >=2.0"]',
    })

    assert _declared_technology(entity, _TECH_ATTRS, 2) == "Python, FastAPI"


def test_a_version_specifier_is_dropped() -> None:
    entity = _Attributed(**{"Programming Languages & Versions": '["TypeScript >=5.7"]'})

    assert _declared_technology(entity, _TECH_ATTRS, 2) == "TypeScript"


def test_a_list_valued_attribute_is_read_whether_or_not_it_is_json_encoded() -> None:
    """Attribute values reach the record as authored, and both shapes are live in one repository."""
    encoded = _Attributed(**{"Programming Languages & Versions": '["Python"]'})
    plain = _Attributed(**{"Programming Languages & Versions": ["Python"]})
    scalar = _Attributed(**{"Programming Languages & Versions": "Python"})

    assert _declared_technology(encoded, _TECH_ATTRS, 2) == "Python"
    assert _declared_technology(plain, _TECH_ATTRS, 2) == "Python"
    assert _declared_technology(scalar, _TECH_ATTRS, 2) == "Python"


def test_an_entity_declaring_nothing_gets_no_line() -> None:
    assert _declared_technology(_Attributed(), _TECH_ATTRS, 2) == ""
    assert _declared_technology(_Attributed(**{"Frameworks & Versions": "[]"}), _TECH_ATTRS, 2) == ""


def test_a_type_declaring_no_attributes_reads_none() -> None:
    """The names belong to a specialization catalogue, so a diagram type that names none gets none
    rather than the resolver reaching for another module's vocabulary on its own."""
    entity = _Attributed(**{"Programming Languages & Versions": '["Python"]'})

    assert _declared_technology(entity, (), 2) == ""
    assert _declared_technology(entity, _TECH_ATTRS, 0) == ""


def test_a_repeated_entry_is_not_said_twice() -> None:
    entity = _Attributed(**{
        "Programming Languages & Versions": '["Python >=3.13"]',
        "Frameworks & Versions": '["Python >=3.13","FastAPI"]',
    })

    assert _declared_technology(entity, _TECH_ATTRS, 2) == "Python, FastAPI"


# ---------------------------------------------------------------------------
# Nesting, at any depth
# ---------------------------------------------------------------------------


def test_a_three_level_chain_keeps_what_is_innermost() -> None:
    """The first version attached each child to its parent's *pre-`replace`* object, so a host
    holding a container holding an application kept the container and silently dropped its
    contents. Nothing failed; a diagram simply came back missing its inside."""
    items = [
        _item("host", "node", "Host"),
        _item("runtime", "node", "Container"),
        _item("app", "container", "App"),
    ]

    nested = _nest(items, (("runtime", "host"), ("app", "runtime")))

    assert [i.local_id for i in nested] == ["host"]
    assert [c.local_id for c in nested[0].children] == ["runtime"]
    assert [c.local_id for c in nested[0].children[0].children] == ["app"]


def test_a_containment_cycle_stops_rather_than_recursing_forever() -> None:
    items = [_item("a", "node", "A"), _item("b", "node", "B")]

    nested = _nest(items, (("a", "b"), ("b", "a")))

    assert nested == [] or all(i.local_id in {"a", "b"} for i in nested)


def test_an_unnested_list_is_returned_unchanged() -> None:
    items = [_item("one", "container", "One"), _item("two", "container", "Two")]

    assert _nest(items, ()) == items


def test_the_renderer_nests_a_node_inside_a_node() -> None:
    body = _render(
        {"c4": {
            "scope_entity_type": "software-system",
            "scope_render_mode": "deployment",
            "puml_stdlib": "C4_Deployment",
        }},
        _ResolvedState(
            scope_items=(_item("sys", "software-system", "System"),),
            scope_render_mode="deployment",
            internal_items=[
                _item(
                    "host", "node", "Docker Host", technology="Technology Node",
                    children=(
                        _item(
                            "runtime", "node", "App Container", technology="Technology Node",
                            children=(_item("api", "container", "API", technology="Python"),),
                        ),
                    ),
                )
            ],
        ),
    )

    assert 'Deployment_Node(HOST, "Docker Host", "Technology Node") {' in body
    assert '  Deployment_Node(RUNTIME, "App Container", "Technology Node") {' in body
    assert '    Container(API, "API", "Python")' in body
    # A hidden edge that crosses a cluster wall crashes GraphViz shape-dependently, so each chain
    # stays inside the boundary that owns it.
    assert "HOST -[hidden]" not in body
