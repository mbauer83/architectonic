"""A small model drawn several ways, each picture rendered through the product's own path.

For tests that read a rendered picture's geometry. The model is written with the same tools an
author uses, the diagrams are created the same way, and each picture is what PlantUML draws for the
stored body — so what the reader is tested against is what the product actually renders, with the
ontology's stereotypes, glyphs, icons and specialization lines in it.

One model, because the scenes differ in how it is drawn, not in what it holds: a process composing
two functions (drawn as a container), an and- and an or-junction, a role with a specialization, a
node with an icon of its own, and relations between them.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from src.application.viewpoints.diagram_reading_lens import ReadingLens, apply_reading_lens
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.rendering._archimate_includes import ArchimateDeclarations
from src.infrastructure.rendering.diagram_legend_for_reading import body_with_reading_legend
from src.infrastructure.rendering.generate_static_includes import generate_static_includes
from src.infrastructure.rendering.puml_runtime import render_puml_svg
from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file

DIAGRAM_TYPE = "archimate-layered"

_ICON_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8">'
    b'<rect width="8" height="8" fill="#ff6600"/></svg>'
)

#: The occurrence id the *occurrence* scene gives the role's second drawing.
SECOND_CLERK = "occ-clerk-again"


def plantuml_available() -> bool:
    try:
        from src.application.verification.artifact_verifier_syntax import find_plantuml_jar  # noqa: PLC0415

        return find_plantuml_jar() is not None
    except Exception:  # noqa: BLE001
        return False


def alias_of(artifact_id: str) -> str:
    """The alias a generated body declares an entity under."""
    prefix_part, random_part, *_ = artifact_id.split(".")
    return f"{prefix_part.split('@', 1)[0]}_{random_part}"


@dataclass(frozen=True)
class RenderedScene:
    """One diagram of the model: the file it is stored in, and the picture PlantUML drew for it."""

    path: Path
    body: str
    svg: str


@dataclass(frozen=True)
class RenderedModel:
    """The model's entity ids by nickname, and each scene drawn from it."""

    repo: Path
    ids: dict[str, str]
    scenes: dict[str, RenderedScene]

    def alias(self, nickname: str) -> str:
        return alias_of(self.ids[nickname])


def _entity(repo: Path, artifact_type: str, name: str, **extra: object) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type, name=name, summary=f"Summary for {name}", dry_run=False,
        repo_root=str(repo), **extra,
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _connect(repo: Path, source: str, connection_type: str, target: str) -> None:
    result = mcp.artifact_add_connection(
        source_entity=source, connection_type=connection_type, target_entity=target, dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result


def _scene(repo: Path, name: str, entity_ids: list[str], **statements: object) -> RenderedScene:
    created = mcp.artifact_create_diagram(
        diagram_type=DIAGRAM_TYPE, name=name, entity_ids=entity_ids, dry_run=False, repo_root=str(repo),
        **statements,
    )
    assert created["wrote"], created
    path = Path(str(created["path"]))
    body = parse_diagram_file(path).puml_body
    svg, warnings = render_puml_svg(body, repo, DIAGRAM_TYPE)
    assert svg is not None, f"{name}: render produced nothing — {warnings}"
    return RenderedScene(path=path, body=body, svg=svg)


class _NoReads:
    """A lens colours by an attribute, so it never follows a connection."""

    def get_entity(self, artifact_id: str) -> None:
        return None

    def get_connection(self, artifact_id: str) -> None:
        return None

    def find_connections_for(self, entity_id: str, **kwargs: object) -> list:
        return []


def _read_through_a_lens(repo: Path, authored: RenderedScene, scored: dict[str, int]) -> RenderedScene:
    """*authored* as a reader sees it when colouring by a score, printing it, and asking for the legend.

    The lens restyles the body before PlantUML runs, so what it adds — a fill, a printed line in a
    label, a legend drawn into the image — is in the picture a layout would be harvested from.
    """
    lens = ReadingLens(colour_by="risk_score", printed=("risk_score",), legend=True)
    entities = [
        EntityRecord(
            artifact_id=f"FNC@{alias}", artifact_type="function", name=alias, version="0.1.0", status="active",
            domain="common", subdomain="", path=Path("e.md"), keywords=(), extra={}, content_text="",
            display_blocks={}, display_label=alias, display_alias=alias, specializations=(),
            attributes={"risk_score": score},
        )
        for alias, score in scored.items()
    ]
    registries = RegistrySnapshot(
        known_entity_types=frozenset({"function"}), known_connection_types=frozenset(),
        known_specialization_slugs=frozenset(), entity_attribute_types={"risk_score": "integer"},
        connection_attribute_types={}, entity_attribute_enums={}, connection_attribute_enums={},
        symmetric_connection_types=frozenset(),
    )
    lensed = apply_reading_lens(
        authored.body, entities, lens=lens, read_access=_NoReads(),  # type: ignore[arg-type]
        registries=registries,
    )
    body = body_with_reading_legend(lensed, lens=lens, declarations=ArchimateDeclarations.from_repo(repo))
    svg, warnings = render_puml_svg(body, repo, DIAGRAM_TYPE)
    assert svg is not None, f"lensed render produced nothing — {warnings}"
    return RenderedScene(path=authored.path, body=body, svg=svg)


def _turned_left_to_right(body: str) -> str:
    lines = body.splitlines()
    title_at = next(index for index, line in enumerate(lines) if line.startswith("title "))
    turned = [*lines[: title_at + 1], "left to right direction", *lines[title_at + 1 :]]
    return "\n".join(turned) + "\n"


def build_rendered_model(root: Path) -> RenderedModel:
    """Write the model under *root* and draw every scene of it."""
    repo = root / "engagements" / "ENG-PIC" / "architecture-repository"
    for directory in ("model", "docs", "diagram-catalog/diagrams"):
        (repo / directory).mkdir(parents=True)
    generate_static_includes(repo)

    ids = {
        "process": _entity(repo, "process", "Handle Order"),
        "check": _entity(repo, "function", "Check Stock"),
        "ship": _entity(repo, "function", "Ship Goods"),
        "bill": _entity(repo, "function", "Bill Customer"),
        "both": _entity(repo, "and-junction", "Both"),
        "either": _entity(repo, "or-junction", "Either"),
        "customer": _entity(repo, "business-actor", "Customer Placing An Order"),
        "clerk": _entity(repo, "role", "Clerk", specializations=["business-role"]),
        "orders": _entity(repo, "application-component", "Order System"),
        "billing": _entity(repo, "application-component", "Billing"),
        "broker": _entity(repo, "technology-node", "Broker"),
    }
    for source, connection_type, target in (
        ("process", "archimate-composition", "check"),
        ("process", "archimate-composition", "ship"),
        ("check", "archimate-flow", "both"),
        ("both", "archimate-flow", "ship"),
        ("process", "archimate-composition", "bill"),
        ("check", "archimate-triggering", "either"),
        ("either", "archimate-triggering", "ship"),
        ("either", "archimate-triggering", "bill"),
        ("customer", "archimate-association", "process"),
        ("customer", "archimate-assignment", "clerk"),
        ("clerk", "archimate-assignment", "process"),
        ("orders", "archimate-association", "process"),
        ("orders", "archimate-association", "billing"),
        ("broker", "archimate-serving", "orders"),
    ):
        _connect(repo, ids[source], connection_type, ids[target])

    everything = list(ids.values())
    icon = {"name": "Broker", "content_base64": base64.b64encode(_ICON_SVG).decode(), "source_format": "svg"}
    top_to_bottom = _scene(
        repo, "Order handling", everything,
        diagram_entities={"icons": {"broker": icon}, "display_icons": {ids["broker"]: "local:broker"}},
    )
    scenes = {
        "top-to-bottom": top_to_bottom,
        # A generated ArchiMate body states no direction, so the other one is a body an author
        # turned by hand — which is also the only left-to-right ArchiMate picture there is to read.
        "left-to-right": _scene(
            repo, "Order handling sideways", everything,
            puml=_turned_left_to_right(top_to_bottom.body),
            diagram_entities={"icons": {"broker": icon}, "display_icons": {ids["broker"]: "local:broker"}},
        ),
        "occurrence": _scene(
            repo, "Order handling with the clerk twice", everything,
            diagram_entities={"occurrence": [{"id": SECOND_CLERK, "backing_entity_id": ids["clerk"]}]},
        ),
        "groupings": _scene(
            repo, "Order handling grouped", everything,
            authored_groupings=[{
                "label": "Front / Office",
                "entity-ids": [ids["customer"]],
                "groups": [{"label": "Desk", "entity-ids": [ids["clerk"]]}],
            }],
        ),
    }
    # Several unrelated elements of one type are what the renderer boxes by type.
    services = [_entity(repo, "service", f"Service {letter}") for letter in "ABC"]
    scenes["type-boxes"] = _scene(repo, "Services and components", [*services, ids["orders"], ids["billing"]])
    scenes["reading-lens"] =_read_through_a_lens(
        repo, top_to_bottom, {alias_of(ids["check"]): 1, alias_of(ids["ship"]): 5, alias_of(ids["bill"]): 9}
    )
    return RenderedModel(repo=repo, ids=ids, scenes=scenes)
