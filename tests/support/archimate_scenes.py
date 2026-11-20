"""One small model drawn every way the ArchiMate body generator knows, with fixed identities.

For tests that hold a *body* — the generated PlantUML text — rather than a picture. Every id and
alias is stated, so a body is the same text on every run and can be compared byte for byte with one
kept from before a change. The scenes cover what decides a body's shape: one domain and several,
flows and flowless components, elements nested by composition, junctions, boxes by type, further
occurrences and the arrows routed to them, labels a diagram gives its instances, listed groupings
flat, nested, across domains and holding an occurrence, and the two sizes at which the generator
drops its hidden ordering chains.

Imports nothing a body generator of an earlier revision lacks, on purpose: the bodies kept under
``tests/fixtures/archimate_bodies`` were written by running this module against that revision.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord

DIAGRAM_TYPE = "archimate-layered"


def entity(key: str, artifact_type: str, name: str, *, specializations: tuple[str, ...] = ()) -> EntityRecord:
    """A model element with a fixed id and alias, both derived from *key*."""
    prefix = "".join(part[0] for part in artifact_type.split("-")).upper().ljust(3, "X")[:3]
    artifact_id = f"{prefix}@1700000000.{key}.{name.lower().replace(' ', '-')}"
    alias = f"{prefix}_{key}"
    return EntityRecord(
        artifact_id=artifact_id, artifact_type=artifact_type, name=name, version="0.1.0", status="draft",
        domain="common", subdomain="", path=Path(f"/model/{artifact_id}.md"), keywords=(), extra={},
        content_text="", display_blocks={"archimate": f'```yaml\nlabel: "{name}"\nalias: {alias}\n```'},
        display_label=name, display_alias=alias, specializations=specializations,
    )


def connection(source: EntityRecord, conn_type: str, target: EntityRecord) -> ConnectionRecord:
    return ConnectionRecord(
        artifact_id=f"{source.artifact_id}---{target.artifact_id}@@archimate-{conn_type}",
        source=source.artifact_id, target=target.artifact_id, conn_type=f"archimate-{conn_type}",
        version="0.1.0", status="draft", path=Path("/model/x.outgoing.md"), extra={}, content_text="",
    )


@dataclass(frozen=True)
class Scene:
    """What one diagram states, as the body generator is handed it."""

    name: str
    entities: tuple[EntityRecord, ...]
    connections: tuple[ConnectionRecord, ...] = ()
    statements: Mapping[str, object] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return self.name.lower().replace(" ", "-")


E = {
    "process": entity("prc001", "process", "Handle Order"),
    "check": entity("fnc001", "function", "Check Stock"),
    "ship": entity("fnc002", "function", "Ship Goods"),
    "bill": entity("fnc003", "function", "Bill Customer"),
    "both": entity("jct001", "and-junction", "Both"),
    "either": entity("jct002", "or-junction", "Either"),
    "customer": entity("act001", "business-actor", "Customer Placing An Order"),
    "clerk": entity("rol001", "role", "Clerk", specializations=("business-role",)),
    "orders": entity("app001", "application-component", "Order System"),
    "billing": entity("app002", "application-component", "Billing"),
    "broker": entity("nod001", "technology-node", "Broker"),
    "driver": entity("drv001", "driver", "Late Deliveries"),
    "goal": entity("gol001", "goal", "Deliver On Time"),
    "requirement": entity("req001", "requirement", "Track Every Parcel"),
}
_SERVICES = tuple(entity(f"srv{index:03d}", "service", f"Service {index}") for index in range(1, 4))
_MANY_SERVICES = tuple(entity(f"srw{index:03d}", "service", f"Wide Service {index}") for index in range(1, 103))
_BOXED_SERVICES = tuple(entity(f"srb{index:03d}", "service", f"Boxed Service {index}") for index in range(1, 27))

_RELATIONS = (
    connection(E["process"], "composition", E["check"]),
    connection(E["process"], "composition", E["ship"]),
    connection(E["check"], "flow", E["both"]),
    connection(E["both"], "flow", E["ship"]),
    connection(E["process"], "composition", E["bill"]),
    connection(E["check"], "triggering", E["either"]),
    connection(E["either"], "triggering", E["ship"]),
    connection(E["either"], "triggering", E["bill"]),
    connection(E["customer"], "association", E["process"]),
    connection(E["customer"], "assignment", E["clerk"]),
    connection(E["clerk"], "assignment", E["process"]),
    connection(E["orders"], "association", E["process"]),
    connection(E["orders"], "association", E["billing"]),
    connection(E["broker"], "serving", E["orders"]),
)
_ORDER_HANDLING = tuple(E[key] for key in (
    "process", "check", "ship", "bill", "both", "either", "customer", "clerk", "orders", "billing", "broker",
))
_CLERK_AGAIN = "occ-clerk-again"
_CLERK_SERVES = connection(E["clerk"], "assignment", E["process"])


def _ids(*keys: str) -> list[str]:
    return [E[key].artifact_id for key in keys]


SCENES: tuple[Scene, ...] = (
    Scene("Order handling", _ORDER_HANDLING, _RELATIONS),
    Scene(
        "Why we track parcels",
        (E["driver"], E["goal"], E["requirement"]),
        (connection(E["driver"], "influence", E["goal"]), connection(E["requirement"], "realization", E["goal"])),
    ),
    Scene("Services and components", (*_SERVICES, E["orders"], E["billing"])),
    Scene("Loose ends", (E["customer"], E["clerk"], E["broker"], *_SERVICES)),
    Scene(
        "The clerk twice", _ORDER_HANDLING, _RELATIONS,
        {
            "diagram_entities": {"occurrence": [{"id": _CLERK_AGAIN, "backing_entity_id": E["clerk"].artifact_id}]},
            "diagram_connections": [{"artifact_id": _CLERK_SERVES.artifact_id, "source-occurrence": _CLERK_AGAIN}],
        },
    ),
    Scene(
        "Short labels", _ORDER_HANDLING, _RELATIONS,
        {"diagram_entities": {
            "display_labels": {E["customer"].artifact_id: "Customer", E["orders"].artifact_id: "OMS"},
        }},
    ),
    Scene(
        "One listed grouping", _ORDER_HANDLING, _RELATIONS,
        {"authored_groupings": [{"label": "Front Office", "entity-ids": _ids("customer", "clerk")}]},
    ),
    Scene(
        "Groupings nested and across domains", _ORDER_HANDLING, _RELATIONS,
        {"authored_groupings": [
            {"label": "Front / Office", "entity-ids": _ids("customer"),
             "groups": [{"label": "Desk", "entity-ids": _ids("clerk")}]},
            {"label": "Systems", "stereotype": "", "entity-ids": _ids("orders", "broker")},
            {"label": "Taken out of the process", "entity-ids": _ids("bill")},
            {"label": "Names nobody", "entity-ids": ["APP@1700000000.nobody"]},
        ]},
    ),
    Scene(
        "A grouping holding an occurrence", _ORDER_HANDLING, _RELATIONS,
        {
            "diagram_entities": {"occurrence": [{"id": _CLERK_AGAIN, "backing_entity_id": E["clerk"].artifact_id}]},
            "authored_groupings": [
                {"label": "Desk", "entity-ids": [E["clerk"].artifact_id]},
                {"label": "Back Office", "stereotype": "Grouping", "entity-ids": [_CLERK_AGAIN, *_ids("billing")]},
            ],
        },
    ),
    Scene(
        "More boxed members than the chain budget", (*_BOXED_SERVICES, E["orders"]), (),
        {"authored_groupings": [
            {"label": "First half", "entity-ids": [service.artifact_id for service in _BOXED_SERVICES[:13]]},
            {"label": "Second half", "entity-ids": [service.artifact_id for service in _BOXED_SERVICES[13:]]},
        ]},
    ),
    Scene("More elements than chains are kept for", (*_MANY_SERVICES, E["orders"], E["customer"])),
)
