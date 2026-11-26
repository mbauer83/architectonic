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
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.application.modeling.binding_normalize import restore_diagram_shorthand
from src.application.modeling.hand_drawn_constructs import hand_drawn
from src.application.verification.drawn_relations import diagram_body_is_reconcile_owned
from src.domain.diagrams.diagram_type_field import diagram_type_of
from src.domain.modules.catalogs import DiagramTypeCatalog
from src.domain.repository.frontmatter import body_after_frontmatter, parse_frontmatter
from src.infrastructure.diagram_composition import CompositionRefused, DiagramComposition, render_composition


class BodyWrittenByHand(CompositionRefused):
    """A replacement that would discard a body written by hand, without saying to give it up."""

    def __init__(self, artifact_id: str, why: str) -> None:
        super().__init__(
            f"Diagram '{artifact_id}' keeps a body written by hand: {why}. A replacement writes the body its "
            "composition generates and would discard that. Edit the PlantUML body instead, or state "
            "manual_layout: false to give the hand-written body up for a generated one.",
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


def written_by_hand(
    frontmatter: Mapping[str, object], body: str, *, repo: Any, repo_root: Path, diagram_types: DiagramTypeCatalog,
) -> str | None:
    """Why the diagram stating *frontmatter* over *body* keeps a body the generator may not write again, or None
    where the body is the generator's.

    Compared only where the body is composed from the model (`diagram_body_is_reconcile_owned`). A type whose
    body is rendered from its own records, or drawn by a projector, has no hand-written body to keep: its
    body is that rendering, in a form this comparison does not read alike.
    """
    if frontmatter.get("manual-layout") is True:
        return "it is manual-layout"
    if not diagram_body_is_reconcile_owned(frontmatter, diagram_types):
        return None
    generated = render_composition(stored_composition(frontmatter), repo=repo, repo_root=repo_root).puml
    drawn = hand_drawn(body, generated)
    return f"it draws what its composition does not generate — {drawn.described()}" if drawn else None


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
