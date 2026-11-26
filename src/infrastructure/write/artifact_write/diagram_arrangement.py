"""Arrange a diagram by intents: compiled in the domain (`arrange_intents`), written as one diagram edit.

The intents apply to the layout a hand-made patch would (`diagram_layout_patch`): the stored one, or —
where PlantUML still arranges the diagram and an intent states geometry — its first layout. Grouping
intents alone state no geometry, so a diagram PlantUML arranges stays so.

Layout intents alone write the layout. Grouping intents change what the diagram holds, so the write is
the one a canvas save makes when its membership changes (D12): the body regenerated for the new
groupings (`rendered_membership`), and in the same edit the layout pruned to what the diagram now holds,
with every box it does not state — a created grouping's, one whose members changed — fitted round its
members on the new picture.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from src.application.modeling.diagram_identities import diagram_identities, strings_of
from src.application.modeling.diagram_layout_statement import DeclaresElementKinds
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.domain.artifact_id import stable_id
from src.domain.diagrams.layout.arrange_intents import ArrangeIntent, arranged, arranges
from src.domain.diagrams.layout.geometry import Extent
from src.domain.diagrams.layout.layout_block import Layout, MalformedLayout, layout_as_written
from src.domain.diagrams.layout.layout_checks import DiagramIdentities
from src.domain.diagrams.layout.layout_intents import patch_between
from src.infrastructure.rendering.layout.diagram_geometry import read_and_measured
from src.infrastructure.rendering.layout.diagram_picture import NotDrawn, placed_on_its_picture

from .diagram_edit import edit_diagram
from .diagram_layout_patch import FirstLayout, LayoutPatchResult, arranged_by, matched_to, stored_diagram
from .diagram_membership import RenderedMembership, rendered_membership
from .parse_existing import ParsedDiagram


def arrange_diagram(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    assert_write_root: Callable[[Path], None],
    store: object,
    artifact_id: str,
    stated: object,
    ontology: DeclaresElementKinds,
    first_layout: FirstLayout,
    dry_run: bool,
) -> LayoutPatchResult:
    """Apply the intents *stated* to *artifact_id* and write the result, for REST and MCP alike.

    Raises MalformedLayout for intents that are not well formed, NotDrawn where the diagram's picture
    cannot be drawn to measure them, and ValueError for one that cannot apply.
    """
    parsed = stored_diagram(repo_root, verifier, artifact_id)
    intents, drawn = _read_against_its_picture(stated, parsed, artifact_id, repo_root, ontology)
    frontmatter = parsed.frontmatter
    stored, base = arranged_by(parsed, first_layout, taking_over=arranges(intents))
    groupings = frontmatter.get("authored-groupings")
    result = arranged(
        intents, groupings=groupings if isinstance(groupings, list) else [],
        diagram_id=stable_id(str(frontmatter.get("artifact-id", artifact_id))), layout=base, drawn=drawn,
    )
    layout, membership, source = result.layout, None, None
    if result.groupings is not None:
        membership = _regenerated(repo_root, store, verifier, artifact_id, frontmatter, result.groupings)
        source = membership.puml
        statements = {
            **frontmatter, "entity-ids-used": membership.entity_ids_used,
            "connection-ids-used": membership.connection_ids_used,
            "authored-groupings": membership.authored_groupings,
        }

        def place(stated: Layout) -> Layout:
            nonlocal source
            source, placed = placed_on_its_picture(
                membership.puml, statements, stated, new=frozenset(), repo_root=repo_root, ontology=ontology,
            )
            return placed

        layout = matched_to(layout, _identities(frontmatter, membership), place)
    block = layout_as_written(layout)
    write = edit_diagram(
        assert_write_root=assert_write_root, repo_root=repo_root, verifier=verifier,
        clear_repo_caches=clear_repo_caches, artifact_id=artifact_id, puml=source,
        entity_ids_used=membership.entity_ids_used if membership else None,
        connection_ids_used=membership.connection_ids_used if membership else None,
        authored_groupings=membership.authored_groupings if membership else None, layout=block, dry_run=dry_run,
    )
    return LayoutPatchResult(
        write, block, patch_between(base, layout, stored=stored),
        membership.authored_groupings if membership else None,
    )


def _read_against_its_picture(
    stated: object, parsed: ParsedDiagram, artifact_id: str, repo_root: Path, ontology: DeclaresElementKinds,
) -> tuple[tuple[ArrangeIntent, ...], dict[str, Extent]]:
    """The intents *stated*, and each element's extent as drawn now, for the sizes a layout entry omits."""
    try:
        return read_and_measured(stated, parsed, artifact_id, repo_root, ontology)
    except MalformedLayout:
        raise
    except ValueError as refusal:  # the picture could not be drawn to measure the intents against
        raise NotDrawn(str(refusal)) from refusal


def _regenerated(
    repo_root: Path, store: object, verifier: ArtifactVerifier, artifact_id: str,
    frontmatter: Mapping[str, object], groupings: list[dict[str, object]],
) -> RenderedMembership:
    """The body for *groupings*, over the diagram's own membership stated — so it draws what it drew."""
    return rendered_membership(
        repo_root=repo_root, store=store, verifier=verifier, artifact_id=artifact_id,
        entity_ids=strings_of(frontmatter.get("entity-ids-used")),
        connection_ids=strings_of(frontmatter.get("connection-ids-used")), authored_groupings=groupings,
    )


def _identities(frontmatter: Mapping[str, object], membership: RenderedMembership) -> DiagramIdentities:
    return diagram_identities(
        entity_ids_used=membership.entity_ids_used, connection_ids_used=membership.connection_ids_used,
        diagram_entities=frontmatter.get("diagram-entities"), diagram_connections=frontmatter.get("connections"),
        authored_groupings=membership.authored_groupings, bindings=frontmatter.get("bindings"),
    )
