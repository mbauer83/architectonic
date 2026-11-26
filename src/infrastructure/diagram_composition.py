"""A diagram composition — what a diagram draws — rendered, and a diagram replaced with it: one save.

What the REST diagram routes (preview, create, replace) and the MCP canvas save share: the body that
states a composition, the one rendering of it, the layout a replacement stores (its whole block, or a
patch reconciled with the new membership, D12), and the replacement itself, with any model commands in
the same staged write. Here, below both transports, so the two cannot come to save a canvas differently.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from src.application.modeling.diagram_identities import diagram_identities, drawn_instances, strings_of
from src.application.modeling.diagram_layout_statement import DeclaresElementKinds
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.artifact_id import stable_conn_id
from src.domain.diagrams.grouping_intents import Nest, Unnest, regrouped
from src.domain.diagrams.layout.arrange_intents import read_intents
from src.domain.diagrams.layout.layout_block import LAYOUT_KEY, Layout, read_layout
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.artifact_home_wire import Rehomeable
from src.infrastructure.diagram_layout_wire import LayoutPatch, RegroupIntent, stated_intents
from src.infrastructure.rendering.diagram_selection import resolve_diagram_selection
from src.infrastructure.rendering.layout.diagram_picture import placed_on_its_picture
from src.infrastructure.write.artifact_write.boundary import assert_engagement_write_root
from src.infrastructure.write.artifact_write.canvas_commands import CanvasCommand
from src.infrastructure.write.artifact_write.diagram_layout_patch import reconciled_layout
from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file
from src.infrastructure.write.artifact_write.types import WriteResult


class CompositionRefused(ValueError):
    """A composition the caller has to correct, naming the field at fault."""

    def __init__(self, message: str, *, field: str) -> None:
        super().__init__(message)
        self.field = field


class DiagramNotStored(ValueError):
    """The diagram a replacement names is not stored."""


class _Body(BaseModel):
    """`extra="forbid"`, and no identity field: identity is in the path, and a body that also
    accepted it would give the caller two places to say which diagram they meant."""

    model_config = ConfigDict(extra="forbid")


class DiagramComposition(BaseModel):
    """What a diagram draws, declared once for every surface that renders one.

    Preview, create and replace all render the *same* picture, so the fields describing it belong in
    one place. They were declared three times, and the cost showed: `authored_groupings` reached
    create and replace while preview kept its own copy of the field list, so a diagram's custom boxes
    appeared in the written diagram and never in the preview of it. A preview missing a field is a
    picture of a diagram the write will not make, which is worse than no preview at all.

    Fields the *operation* decides — a version, a status, whether it is a dry run — stay on the body
    that decides them. This carries only what ends up in the picture.
    """

    diagram_type: str
    name: str
    entity_ids: list[str]
    connection_ids: list[str]
    diagram_entities: dict[str, Any] | None = None
    authored_groupings: list[dict[str, Any]] | None = None
    #: Nest and unnest intents (as the arrange route takes them), applied to `authored_groupings` as the
    #: body is read: what an editor kept of moving elements into and out of the diagram's own boxes,
    #: compiled by the one grouping compiler (`grouping_intents.regrouped`). Applied here, every surface
    #: that renders or writes a composition reads the same groupings, and none can forget the intents.
    grouping_intents: list[RegroupIntent] | None = None
    #: The boxes the grouping intents changed the members of: their stored placement no longer fits, so a
    #: replacement fits them again round their members, as the arrange route does.
    _refit: frozenset[str] = PrivateAttr(default_factory=frozenset)

    @model_validator(mode="after")
    def _regrouped(self) -> Self:
        """The groupings after the intents, in order; refuses one that cannot apply, saying why.

        Only moving instances between groupings is taken here: creating or deleting a grouping, and any
        intent that states geometry, is the arrange route's.
        """
        if not self.grouping_intents:
            return self
        groupings: list[object] = list(self.authored_groupings or [])
        refit: set[str] = set()
        for intent in read_intents(stated_intents(self.grouping_intents)):
            if not isinstance(intent, Nest | Unnest):
                kind = type(intent).__name__
                raise ValueError(f"A composition takes nest and unnest intents only; {kind} is the arrange route's.")
            # No grouping is created here, so no grouping id is seeded from the diagram's.
            result = regrouped(intent, groupings, diagram_id="")
            groupings, refit = [*result.groupings], refit | result.refit | result.removed
        self.authored_groupings = [dict(grouping) for grouping in groupings if isinstance(grouping, dict)]
        self.grouping_intents = None
        self._refit = frozenset(refit)
        return self

    @property
    def refit(self) -> frozenset[str]:
        """The boxes whose members the grouping intents changed."""
        return self._refit


class DiagramReplacement(DiagramComposition, _Body, Rehomeable):
    """A diagram replaced whole: its composition, its layout, and the model commands saved with it."""

    commands: list[CanvasCommand] = Field(
        default_factory=list,
        description=(
            "Model edits saved in the same write as the diagram: model.element.create / rename / edit / delete, "
            "model.relation.create / edit. All land or none do."
        ),
    )
    #: The whole layout block to store. Absent keeps the diagram's own; an empty object removes it
    #: and returns the diagram to PlantUML's arrangement with nothing else changed.
    layout: dict[str, Any] | None = None
    #: Instead of a whole block: entries of the layout patch (as `PATCH …/layout` takes them), applied to
    #: the stored layout in the same write that changes the membership, which then drops whatever names
    #: what the diagram no longer holds (D12). So the stored layout always matches the body written.
    layout_patch: LayoutPatch | None = None
    manual_layout: bool | None = Field(
        default=None,
        description=(
            "false gives a manual-layout diagram's hand-written body up: the body is generated from the "
            "composition from then on, and the diagram can be laid out. Absent keeps the diagram's own."
        ),
    )
    version: str | None = None
    status: str | None = None
    tlp: str | None = None
    viewpoint: dict[str, Any] | None = None
    dry_run: bool = True


def _split_diagram_entities(
    diagram_entities: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None]:
    """Separate the transport-only `_connections` key from entity data."""
    if diagram_entities is None:
        return None, None
    conns = diagram_entities.get("_connections")
    if conns is None:
        return diagram_entities, None
    clean = {k: v for k, v in diagram_entities.items() if k != "_connections"}
    return clean or None, conns if isinstance(conns, list) else None


def _extract_conn_bindings(
    connections: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]]]:
    """Strip `backing_conn_id` from connections; return (clean, binding_dicts)."""
    if not connections:
        return connections, []
    bindings: list[dict[str, Any]] = []
    clean: list[dict[str, Any]] = []
    for conn in connections:
        if not isinstance(conn, dict):
            clean.append(conn)
            continue
        backing_id = conn.get("backing_conn_id")
        conn_id = conn.get("id")
        if backing_id and conn_id:
            bindings.append({
                "id": f"bind-conn-{conn_id}",
                "subject": {"kind": "connection", "id": conn_id},
                "correspondence_kind": "represents",
                "target": {"connection_id": backing_id},
            })
        clean.append({k: v for k, v in conn.items() if k != "backing_conn_id"})
    return clean or None, bindings


@dataclass(frozen=True)
class RenderedComposition:
    """One composition, resolved and rendered — the same way for every surface that shows it."""

    entities: list[Any]
    connections: list[Any]
    entity_ids_used: list[str]
    connection_ids_used: list[str]
    diagram_entities: dict[str, Any] | None
    diagram_connections: list[dict[str, Any]] | None
    conn_bindings: list[dict[str, Any]]
    puml: str

    def statements(self, body: DiagramComposition) -> dict[str, Any]:
        """The membership and grouping declarations that key the rendered picture."""
        return {
            "name": body.name, "diagram-type": body.diagram_type,
            "entity-ids-used": self.entity_ids_used, "connection-ids-used": self.connection_ids_used,
            "diagram-entities": self.diagram_entities, "connections": self.diagram_connections,
            "authored-groupings": body.authored_groupings, "bindings": self.conn_bindings,
        }


def render_composition(
    body: DiagramComposition, *, repo: Any, repo_root: Path,
    proposed_entities: tuple[EntityRecord, ...] = (), proposed_connections: tuple[ConnectionRecord, ...] = (),
) -> RenderedComposition:
    """Resolve a composition and render it, once, for preview and for both writes.

    The three surfaces used to assemble this themselves, and drifted twice over: preview never passed
    `authored_groupings`, so custom boxes were invisible until the write; and preview rendered with
    connection *bindings* still attached while the writes stripped them first, so the two were not
    rendering the same input either. A preview is only worth having if it is the write's own picture.
    """
    from src.infrastructure.icons.diagram_icons import DiagramIconSource  # noqa: PLC0415
    from src.infrastructure.icons.library_source import LibraryIconSource  # noqa: PLC0415
    from src.infrastructure.rendering.diagram_builder import generate_puml_body  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.diagram_body_preparation import with_icons_prepared  # noqa: PLC0415

    entities, connections, entity_ids_used, connection_ids_used = resolve_diagram_selection(
        repo, body.entity_ids, body.connection_ids
    )
    entities.extend(proposed_entities)
    # A draft can change the annotations on an already selected model relation.
    # Preserve its position and its identity in the drawing, as in the eventual write.
    proposals = {stable_conn_id(c.artifact_id): c for c in proposed_connections}
    connections = [proposals.pop(stable_conn_id(c.artifact_id), c) for c in connections]
    connections.extend(proposals.values())
    entity_ids_used.extend(entity.artifact_id for entity in proposed_entities)
    connection_ids_used.extend(connection.artifact_id for connection in proposals.values())
    de, dc = _split_diagram_entities(body.diagram_entities)
    try:
        de = with_icons_prepared(de) if de is not None else None
    except ValueError as exc:  # an upload the normaliser refuses is the caller's to correct
        raise CompositionRefused(str(exc), field="diagram_entities") from exc
    dc, conn_bindings = _extract_conn_bindings(dc)
    puml = generate_puml_body(
        body.name,
        entities,
        connections,
        diagram_type=body.diagram_type,
        repo_root=repo_root,
        diagram_entities=de,
        diagram_connections=dc,
        authored_groupings=body.authored_groupings,
        # The diagram's own icons first, uploads not yet saved included, so a preview draws what the save will.
        icon_source=DiagramIconSource(de, LibraryIconSource(repo)),
    )
    return RenderedComposition(
        entities=entities, connections=connections,
        entity_ids_used=entity_ids_used, connection_ids_used=connection_ids_used,
        diagram_entities=de, diagram_connections=dc, conn_bindings=conn_bindings, puml=puml,
    )


def source_and_layout_to_store(
    artifact_id: str, body: DiagramReplacement, composed: RenderedComposition,
    repo_root: Path, ontology: DeclaresElementKinds, repo: Any,
) -> tuple[str, dict[str, object] | None]:
    """*body*'s whole layout, or its patch applied to the stored one and pruned to the new membership."""
    if body.layout_patch is not None and body.layout is not None:
        raise ValueError("State either layout or layout_patch, not both.")
    if body.layout_patch is None and (body.layout is not None or not body.refit):
        return composed.puml, body.layout
    record = repo.get_diagram(artifact_id)
    if record is None or not Path(record.path).exists():
        raise DiagramNotStored(f"Diagram '{artifact_id}' not found")
    before = parse_diagram_file(Path(record.path)).frontmatter
    patch = body.layout_patch.stated() if body.layout_patch is not None else {}
    # A stored box whose members a grouping intent changed is fitted again, unless the patch places it.
    stored_boxes = read_layout(before[LAYOUT_KEY]).boxes if before.get(LAYOUT_KEY) else {}
    placed = (body.layout_patch.boxes if body.layout_patch is not None else None) or {}
    if refit := [key for key in body.refit if key in stored_boxes and key not in placed]:
        patch["boxes"] = {**patch["boxes"], **dict.fromkeys(refit)} if placed else dict.fromkeys(refit)
    identities = diagram_identities(
        entity_ids_used=composed.entity_ids_used, connection_ids_used=composed.connection_ids_used,
        diagram_entities=composed.diagram_entities, diagram_connections=composed.diagram_connections,
        authored_groupings=body.authored_groupings, bindings=composed.conn_bindings or None,
    )
    previous = drawn_instances(
        strings_of(before.get("entity-ids-used")), before.get("diagram-entities"), before.get("bindings"),
    )
    changed = previous != identities.instances or before.get("authored-groupings") != body.authored_groupings

    source = composed.puml

    def place(layout: Layout) -> Layout:
        nonlocal source
        source, placed = placed_on_its_picture(
            source, composed.statements(body), layout, new=identities.instances - previous,
            repo_root=repo_root, ontology=ontology,
        )
        return placed

    result = reconciled_layout(
        stored=before.get(LAYOUT_KEY), patch=patch, identities=identities,
        place_members=place if changed else None,
    )
    return source, result


#: How a replacement is written once its model commands are staged: over the staged repo, by its verifier.
type SaveInto = Callable[[Path, Any, Any, Callable[[Path], None], bool], WriteResult]


def replace_diagram(
    artifact_id: str, body: DiagramReplacement, *, root: Path, catalogs: RuntimeCatalogs, live_repo: Any,
    live_verifier: Any, clear_caches: Callable[[Path | list[Path]], None],
) -> WriteResult:
    """Replace *artifact_id* with *body*, and its model commands with it, in one write (or one dry run).

    Called inside the transport's authorized write. Raises `LayoutConflict` for a stale layout entry, and
    `ValueError` for anything else it refuses — `refuse_an_unsafe_replacement` says which are checked first.
    """
    from src.application.candidate_repository import committed_repository  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.canvas_commands import canvas_save  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.enterprise_edit_arguments import KEYWORDS_UNSET  # noqa: PLC0415

    def save(repo_root: Path, repo: Any, verifier: Any, clear: Callable[[Path], None], dry_run: bool) -> WriteResult:
        composed = render_composition(body, repo=repo, repo_root=repo_root)
        source, layout = source_and_layout_to_store(
            artifact_id, body, composed, root, catalogs.ontology, live_repo,
        )
        return edit_diagram(
            assert_write_root=assert_engagement_write_root, repo_root=repo_root, verifier=verifier,
            clear_repo_caches=clear, artifact_id=artifact_id, repo=live_repo, puml=source,
            name=body.name, group=body.group, keywords=KEYWORDS_UNSET, diagram_entities=composed.diagram_entities,
            diagram_connections=composed.diagram_connections, entity_ids_used=composed.entity_ids_used,
            connection_ids_used=composed.connection_ids_used, authored_groupings=body.authored_groupings,
            layout=layout, version=body.version, status=body.status, tlp=body.tlp,
            bindings=composed.conn_bindings or None, viewpoint=body.viewpoint, dry_run=dry_run,
            committed_repo=committed_repository(repo), manual_layout=body.manual_layout,
        )

    from src.infrastructure.diagram_replacement_guard import refuse_an_unsafe_replacement  # noqa: PLC0415

    refuse_an_unsafe_replacement(artifact_id, body, repo=live_repo, repo_root=root, catalogs=catalogs)
    if body.commands:
        return canvas_save(body.commands, root, catalogs, body.dry_run, live_repo, save, clear_caches)
    return save(root, live_repo, live_verifier, clear_caches, body.dry_run)
