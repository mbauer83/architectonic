"""Whether a stored diagram's body is the generator's to write again — asked once, by every write that would.

A diagram owns its PlantUML body (ADR@1783406738). A replacement — the canvas save, `PUT /api/diagrams/{id}`
and MCP `artifact_replace_diagram` — writes the body its composition generates, so on a body written by hand
it would discard whatever the hand put there. It did: adding one element on the canvas of a diagram whose
body drew two team boxes and a second drawing of four elements replaced the body with generated type boxes,
and the team boxes were gone from the file.

A body is written by hand when the diagram says so (`manual-layout`), or when it draws something the body
generated from its own stored composition does not (`hand_drawn_constructs`). The second is what a flag
cannot answer for a diagram whose body was supplied as text and never marked. Such a replacement is refused,
naming what would be lost, unless it states `manual_layout: false` — giving the hand-written body up, which
is what the editor's *Lay out automatically* confirms. The diagram read answers the same question, so the
editor offers the canvas only where a save will keep what the diagram draws.

What would be lost is named as a reader sees the picture: boxes by their labels, elements by the names they
are drawn with, relations as `Name → Name (type)`. The comparison works on aliases and arrows, which are the
body's own spelling and mean nothing to whoever is told why a save was refused.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.application.modeling.binding_normalize import restore_diagram_shorthand
from src.application.modeling.diagram_identities import entity_by_alias
from src.application.modeling.hand_drawn_constructs import HandDrawn, hand_drawn
from src.application.puml_alias_declarations import alias_declared_on, label_declared_on
from src.application.verification.drawn_relations import diagram_body_is_reconcile_owned
from src.domain.artifact_id import MalformedArtifactIdError, parse_connection_id
from src.domain.diagrams.diagram_type_field import diagram_type_of
from src.domain.modules.catalogs import DiagramTypeCatalog
from src.domain.repository.frontmatter import body_after_frontmatter, parse_frontmatter
from src.infrastructure.diagram_composition import CompositionRefused, DiagramComposition, render_composition
from src.infrastructure.rendering.archimate_relation_rendering import display_connection_label

#: What an element is called where neither its declaration nor the model gives it a name.
UNNAMED = "an element without a name"


@dataclass(frozen=True)
class NamedRelation:
    """A relation only the hand-drawn picture has, by the names of its two ends and the model's type for it."""

    source: str
    target: str
    #: The relation's type as a reader names it (`assignment`), or None where the diagram's connections do
    #: not give the pair exactly one.
    type: str | None = None

    def __str__(self) -> str:
        drawn = f"{self.source} → {self.target}"
        return f"{drawn} ({self.type})" if self.type else drawn


@dataclass(frozen=True)
class HandWrittenBody:
    """Why a diagram's picture is drawn by hand, named as a reader sees the picture.

    `manual_layout` where the diagram says so; otherwise what the picture draws that its generated picture
    would not.
    """

    manual_layout: bool = False
    boxes: tuple[str, ...] = ()
    elements: tuple[str, ...] = ()
    relations: tuple[NamedRelation, ...] = ()
    directions: tuple[str, ...] = ()

    def reason(self) -> str:
        """Why, as one clause: what follows "the picture is drawn by hand:"."""
        if self.manual_layout:
            return "it is marked manual-layout"
        return f"it draws what a generated picture would not: {self.listed()}"

    def listed(self) -> str:
        """What only the hand-drawn picture has, kind by kind."""
        kinds = (
            ("boxes", [f'"{box}"' for box in self.boxes]),
            ("elements", [f'"{element}"' for element in self.elements]),
            ("relations", [str(relation) for relation in self.relations]),
            ("layout direction", list(self.directions)),
        )
        return "; ".join(f"{noun} {', '.join(found)}" for noun, found in kinds if found)

    def to_mapping(self) -> dict[str, object]:
        """The constructs as the diagram read answers them."""
        return {
            "boxes": list(self.boxes),
            "elements": list(self.elements),
            "relations": [
                {"source": one.source, "target": one.target, **({"type": one.type} if one.type else {})}
                for one in self.relations
            ],
            "directions": list(self.directions),
        }


class BodyWrittenByHand(CompositionRefused):
    """A replacement that would discard a picture drawn by hand, without saying to give it up."""

    def __init__(self, artifact_id: str, why: HandWrittenBody) -> None:
        super().__init__(
            f"Diagram '{artifact_id}' has a picture drawn by hand: {why.reason()}. Saving this replacement "
            "would replace that picture with a generated one. Edit the PlantUML body instead, or state "
            "manual_layout: false to give the hand-drawn picture up.",
            field="manual_layout",
        )


def _strings(value: object) -> list[str]:
    return [str(one) for one in value] if isinstance(value, list) else []


def stated_diagram_entities(frontmatter: Mapping[str, object]) -> dict[str, Any] | None:
    """The diagram's statements about its instances as a composition carries them: the binding shorthand the
    persist path strips restored, and the diagram's own connections under `_connections`. The diagram read
    answers them this way too, so what the editor sends back is what this compares."""
    raw = frontmatter.get("diagram-entities")
    stated = dict(raw) if isinstance(raw, dict) else {}
    stated = restore_diagram_shorthand(stated, frontmatter.get("bindings")) or stated
    if connections := frontmatter.get("connections"):
        stated["_connections"] = connections
    return stated or None


def stored_composition(frontmatter: Mapping[str, object]) -> DiagramComposition:
    """The composition a stored diagram states: what a replacement changing nothing would send."""
    groupings = frontmatter.get("authored-groupings")
    return DiagramComposition(
        diagram_type=diagram_type_of(frontmatter), name=str(frontmatter.get("name", "")),
        entity_ids=_strings(frontmatter.get("entity-ids-used")),
        connection_ids=_strings(frontmatter.get("connection-ids-used")),
        diagram_entities=stated_diagram_entities(frontmatter),
        authored_groupings=[dict(one) for one in groupings if isinstance(one, dict)] if isinstance(groupings, list)
        else None,
    )


def _namer(body: str, frontmatter: Mapping[str, object], repo: Any) -> Callable[[str], str]:
    """How an alias in *body* is named to a reader: the label it is drawn with, else its model element's name."""
    labels = {
        declaration.alias: " ".join(label.replace("\\n", " ").split())
        for line in body.splitlines()
        if (declaration := alias_declared_on(line)) is not None and (label := label_declared_on(line))
    }
    elements = entity_by_alias(frontmatter)

    def name(alias: str) -> str:
        if label := labels.get(alias):
            return label
        entity = repo.get_entity(elements[alias]) if alias in elements else None
        return str(entity.name) if entity is not None and entity.name else UNNAMED

    return name


def _types_by_pair(frontmatter: Mapping[str, object]) -> dict[frozenset[str], set[str]]:
    """The relation types the diagram's model connections give each pair of elements, either way round."""
    found: dict[frozenset[str], set[str]] = {}
    for connection_id in _strings(frontmatter.get("connection-ids-used")):
        try:
            key = parse_connection_id(connection_id)
        except MalformedArtifactIdError:
            continue
        found.setdefault(frozenset((key.src_short, key.tgt_short)), set()).add(key.type)
    return found


def named_hand_drawn(
    drawn: HandDrawn, *, body: str, frontmatter: Mapping[str, object], repo: Any,
) -> HandWrittenBody:
    """*drawn* named as a reader sees the picture, with no alias and no arrow. A relation's type is the
    model's, where the diagram's connections give its two elements exactly one."""
    name = _namer(body, frontmatter, repo)
    elements = entity_by_alias(frontmatter)
    types = _types_by_pair(frontmatter)

    def type_of(source: str, target: str) -> str | None:
        if source not in elements or target not in elements:
            return None
        held = types.get(frozenset((elements[source], elements[target])), set())
        return display_connection_label(next(iter(held))) if len(held) == 1 else None

    relations = (
        NamedRelation(name(one.source_alias), name(one.target_alias), type_of(one.source_alias, one.target_alias))
        for one in drawn.relations
    )
    return HandWrittenBody(
        boxes=drawn.boxes,
        elements=tuple(dict.fromkeys(name(alias) for alias in drawn.elements)),
        relations=tuple(dict.fromkeys(relations)),
        directions=tuple(direction.removesuffix(" direction") for direction in drawn.directions),
    )


def written_by_hand(
    frontmatter: Mapping[str, object], body: str, *, repo: Any, repo_root: Path, diagram_types: DiagramTypeCatalog,
) -> HandWrittenBody | None:
    """Why the diagram stating *frontmatter* over *body* keeps a body the generator may not write again, or None
    where the body is the generator's.

    Compared only where the body is composed from the model (`diagram_body_is_reconcile_owned`). A type whose
    body is rendered from its own records, or drawn by a projector, has no hand-written body to keep: its
    body is that rendering, in a form this comparison does not read alike.
    """
    if frontmatter.get("manual-layout") is True:
        return HandWrittenBody(manual_layout=True)
    if not diagram_body_is_reconcile_owned(frontmatter, diagram_types):
        return None
    generated = render_composition(stored_composition(frontmatter), repo=repo, repo_root=repo_root).puml
    drawn = hand_drawn(body, generated)
    return named_hand_drawn(drawn, body=body, frontmatter=frontmatter, repo=repo) if drawn else None


def refuse_a_hand_written_body(
    artifact_id: str, *, source: str, repo: Any, repo_root: Path, diagram_types: DiagramTypeCatalog,
) -> None:
    """Raise `BodyWrittenByHand` where the stored diagram, whose file is *source*, keeps a body written by hand."""
    why = written_by_hand(
        parse_frontmatter(source), body_after_frontmatter(source), repo=repo, repo_root=repo_root,
        diagram_types=diagram_types,
    )
    if why is not None:
        raise BodyWrittenByHand(artifact_id, why)
