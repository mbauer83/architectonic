"""Diagram refresh / sync — dispatch by diagram ownership.

Refresh semantics vary by diagram kind.  The invariant is that a refresh
*never* silently deletes or blanks a diagram.  Unknown/unsupported combinations
fail without modifying any file.

Dispatch matrix (kind → refresh-op, empty-result, deletion-allowed):

  Model-backed (has ``scoped-by`` / projector):
    refresh = re-run the diagram-type projector;
    empty   = valid empty view OR explicit error;
    delete  = NEVER, not even on empty inference.

  ArchiMate reconcile (explicit refs, no projector):
    refresh = reconcile refs + regenerate PUML;
    empty   = keep diagram, report unresolved refs;
    delete  = only on an explicit delete intent, never silently.

  Standalone (explicit diagram-entities):
    refresh = re-render from stored entities;
    empty   = keep diagram;
    delete  = no.

``sync_diagram_to_model`` in this module implements the ArchiMate-reconcile
path only.  Model-backed (scope-bound) diagrams must be refreshed via
``refresh_diagram``; passing a scope-bound diagram to ``sync_diagram_to_model``
raises ValueError.
"""

from collections.abc import Callable
from pathlib import Path

from src.application.repo_path_helpers import diagram_source_root, resolve_diagram_source_path
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.domain.artifact_id import stable_conn_id
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.rendering.diagram_selection import connections_among

from ._sync_helpers import (
    LookupStore,
    current_reference_spellings,
    dedupe_connections,
    dedupe_entities,
    infer_connections_from_puml,
    infer_entities_from_puml,
    resolve_connections,
    resolve_entities,
)
from .boundary import assert_engagement_write_root
from .coerce import as_optional_str_list
from .diagram_edit import edit_diagram
from .diagram_membership import is_scope_bound, is_standalone
from .parse_existing import parse_diagram_file
from .types import SyncDiagramToModelResult


def refresh_diagram(
    *,
    repo_root: Path,
    store: LookupStore,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    dry_run: bool,
) -> SyncDiagramToModelResult:
    """Refresh a diagram according to its ownership kind (see module-level dispatch matrix).

    Model-backed (scope-bound) diagrams are re-projected from the model — they are
    NEVER deleted.  ArchiMate-reconcile diagrams are delegated to sync_diagram_to_model.
    The ``store`` parameter is only used on the ArchiMate-reconcile path.
    """
    _find = verifier.registry.find_file_by_id if verifier.registry is not None else None
    diagram_path = resolve_diagram_source_path(repo_root, artifact_id, _find)
    if diagram_path is None:
        raise ValueError(f"Diagram '{artifact_id}' not found under {diagram_source_root(repo_root)}")

    parsed = parse_diagram_file(diagram_path)

    if is_scope_bound(parsed) or is_standalone(parsed):
        # Both scope-bound and standalone diagrams are re-rendered from stored state.
        # Neither is ever deleted by a refresh — deletion requires an explicit call.
        #
        # The reference lists are passed so their *spellings* can be brought up to date. This branch
        # used to pass neither, so `entity-ids-used` survived byte for byte and a reference naming an
        # artifact by a slug it had dropped stayed wrong forever: the verifier reported it (W305),
        # told the author to rewrite it, and no operation would. The reconcile branch below has
        # always corrected them, as a side effect of resolving each id to its record.
        #
        # Spellings only — `current_reference_spellings` returns the same ids in the same order, so
        # this adds no membership and removes none, which a refresh must never do.
        fm = parsed.frontmatter
        write_result = edit_diagram(
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=clear_repo_caches,
            artifact_id=artifact_id,
            entity_ids_used=current_reference_spellings(
                as_optional_str_list(fm.get("entity-ids-used")) or [], store
            ),
            connection_ids_used=current_reference_spellings(
                as_optional_str_list(fm.get("connection-ids-used")) or [], store
            ),
            # A refresh is the user asking for the picture to be rebuilt, so the generated
            # ranking is recomputed here and only here. Hand-placed hidden links still
            # survive it — the optimizer replaces its own block, never anyone else's.
            rebuild_layout=True,
            dry_run=dry_run,
        )
        return SyncDiagramToModelResult(
            wrote=write_result.wrote,
            path=write_result.path,
            artifact_id=write_result.artifact_id,
            content=write_result.content,
            warnings=write_result.warnings,
            verification=write_result.verification,
            removed_entity_ids=[],
            removed_connection_ids=[],
            deleted_diagram=False,
        )

    return sync_diagram_to_model(
        repo_root=repo_root,
        store=store,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        dry_run=dry_run,
    )


def _reconciled_authored_groupings(
    fm: dict,
    puml_body: str,
    entity_records: list,
) -> tuple[list[dict[str, object]], list[str]]:
    """The diagram's authored groupings, reconciled against the surviving entities.

    Frontmatter ``authored-groupings`` is authoritative once present. A diagram that
    predates the field migrates its hand-authored grouping rectangles out of the
    body — labeled, alias-less rectangles whose label is NOT one the generator
    produces (element-type plurals, domain titles). Members that left the diagram
    are dropped WITH a warning; an emptied grouping is removed with a warning,
    never silently.
    """
    from src.application.puml_grouping_parsing import parse_labeled_groupings  # noqa: PLC0415
    from src.domain.artifact_id import stable_id  # noqa: PLC0415
    from src.domain.diagrams.recorded_references import pruned_groupings  # noqa: PLC0415

    raw = fm.get("authored-groupings")
    if isinstance(raw, list):
        source: list[dict[str, object]] = [dict(group) for group in raw if isinstance(group, dict)]
    else:
        source = _captured_authored_groupings(puml_body, entity_records, parse_labeled_groupings)

    surviving_short = {stable_id(record.artifact_id) for record in entity_records}
    pruned = pruned_groupings(source, lambda member: stable_id(member) in surviving_short)
    warnings = [
        f"authored grouping '{label}': member {member} left the diagram and was dropped"
        for label, member in pruned.dropped_members
    ] + [
        f"authored grouping '{label}' removed — all its members left the diagram"
        for label in pruned.emptied_labels
    ]
    return pruned.groupings, warnings


def _captured_authored_groupings(puml_body: str, entity_records: list, parse) -> list[dict[str, object]]:
    """Migrate hand-authored grouping rectangles from a body into structured form."""
    from src.application.artifacts.parsing import normalize_puml_alias  # noqa: PLC0415
    from src.domain.diagrams.recorded_references import GROUPING_MEMBERS_KEY  # noqa: PLC0415
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415
    from src.infrastructure.rendering.archimate_entity_declarations import (  # noqa: PLC0415
        ordered_entity_type_groups,
    )

    generated_labels = {label for label, _ in ordered_entity_type_groups(list(entity_records), get_module_registry())}
    generated_labels |= {str(getattr(record, "domain", "") or "").title() for record in entity_records}
    id_by_alias = {
        normalize_puml_alias(record.display_alias): record.artifact_id
        for record in entity_records
        if record.display_alias
    }
    captured: list[dict[str, object]] = []
    for grouping in parse(puml_body):
        if grouping.label in generated_labels:
            continue
        member_ids = [id_by_alias[alias] for alias in grouping.member_aliases if alias in id_by_alias]
        if member_ids:
            captured.append(
                {"label": grouping.label, "stereotype": grouping.stereotype,
                 GROUPING_MEMBERS_KEY: member_ids}
            )
    return captured


def _undrawn_connection_report(
    store: LookupStore,
    entity_records: list[EntityRecord],
    conn_records: list[ConnectionRecord],
) -> list[str]:
    """Say which model connections between two elements the diagram draws are missing from it.

    A reconcile converges in one direction only: it drops what the model no longer has and never
    adopts what the model has gained. That is deliberate — the entity set is the authored thing and
    the picture is the author's, and a bulk delete auto-syncs every dependent diagram, so adopting
    would redraw curated views as a side effect of unrelated maintenance.

    What was wrong is that the other direction was *silent*. A relation added between two elements
    already on the diagram left it out of date, and a sync answered success over a picture that no
    longer said what the model said. So it is reported and not applied: adopting these is one edit,
    stating ``entity_ids``, and that edit is the author's to make.

    Asked through ``connections_among``, which owns "what a diagram of these entities draws" — the
    same rule ``artifact_create_diagram`` and the membership path apply, so this cannot disagree
    with what adopting them would produce. Compared in stable form, because a short and a full
    spelling of an id name the same connection.
    """
    drawn = {stable_conn_id(record.artifact_id) for record in conn_records}
    undrawn = [
        connection_id
        for connection_id in connections_among(store, [record.artifact_id for record in entity_records])
        if stable_conn_id(connection_id) not in drawn
    ]
    if not undrawn:
        return []
    listed = "\n".join(f"  - {connection_id}" for connection_id in undrawn)
    return [
        f"model connections among this diagram's entities that it does not draw ({len(undrawn)}):\n"
        f"{listed}\n"
        "Pass entity_ids with this diagram's current entity list to adopt them into the picture."
    ]


def sync_diagram_to_model(
    *,
    repo_root: Path,
    store: LookupStore,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    dry_run: bool,
) -> SyncDiagramToModelResult:
    """Reconcile an ArchiMate-reconcile diagram against the current model state.

    Reads ``entity-ids-used`` and ``connection-ids-used`` from the diagram's
    frontmatter, looks up each ID in the store, and drops any that no longer
    exist. Renamed entities are detected by matching the stable prefix
    (``TYPE@timestamp.random``) so a name change updates the reference rather
    than removing the entity. Surviving records are passed to
    ``generate_archimate_puml_body`` so names are always current.

    Raises ValueError for scope-bound (model-backed) diagrams — use
    ``refresh_diagram`` for those.
    """
    from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body  # noqa: PLC0415

    assert_engagement_write_root(repo_root)

    _find = verifier.registry.find_file_by_id if verifier.registry is not None else None
    diagram_path = resolve_diagram_source_path(repo_root, artifact_id, _find)
    if diagram_path is None:
        raise ValueError(f"Diagram '{artifact_id}' not found under {diagram_source_root(repo_root)}")

    parsed = parse_diagram_file(diagram_path)
    fm = parsed.frontmatter

    if is_scope_bound(parsed):
        raise ValueError(
            f"Diagram '{artifact_id}' is model-backed (scope-bound). "
            "Use refresh_diagram() — sync_diagram_to_model must not be called on projector-owned diagrams."
        )

    existing_entity_ids: list[str] = as_optional_str_list(fm.get("entity-ids-used")) or []
    existing_conn_ids: list[str] = as_optional_str_list(fm.get("connection-ids-used")) or []
    diagram_type = str(fm.get("diagram-type", "archimate"))
    name = str(fm.get("name", ""))

    fm_entity_records, removed_entity_ids = resolve_entities(existing_entity_ids, store)
    fm_conn_records, removed_conn_ids = resolve_connections(existing_conn_ids, store)
    puml_entity_records, _unresolved_aliases = infer_entities_from_puml(parsed.puml_body, store)
    puml_conn_records, inferred_removed_conn_ids = infer_connections_from_puml(parsed.puml_body, store)

    entity_records = dedupe_entities([*puml_entity_records, *fm_entity_records])
    conn_records = dedupe_connections([*puml_conn_records, *fm_conn_records])
    removed_conn_ids = list(dict.fromkeys([*removed_conn_ids, *inferred_removed_conn_ids]))

    if not entity_records:
        # All referenced entities are unresolved. Preserve the diagram — silent
        # deletion violates the refresh-never-deletes contract.  The caller must
        # explicitly delete the diagram if that is the intent.
        return SyncDiagramToModelResult(
            wrote=False,
            path=diagram_path,
            artifact_id=artifact_id,
            content=None,
            warnings=["All referenced entities are unresolved; diagram preserved. Delete explicitly if intended."],
            verification={"path": str(diagram_path), "file_type": "diagram", "valid": True, "issues": []},
            removed_entity_ids=removed_entity_ids,
            removed_connection_ids=removed_conn_ids,
            deleted_diagram=False,
        )

    raw_el = fm.get("edge-labels")
    existing_edge_labels = dict(raw_el) if isinstance(raw_el, dict) else None
    authored_groupings, grouping_warnings = _reconciled_authored_groupings(fm, parsed.puml_body, entity_records)
    # Reported on both paths below: a hand-laid-out diagram goes out of date the same way, and
    # keeping its body verbatim is a reason to say so, not a reason to stay quiet.
    staleness_warnings = _undrawn_connection_report(store, entity_records, conn_records)

    if fm.get("manual-layout") is True:
        # A hand-tuned picture the user has ruled better than any regeneration:
        # reconcile the BINDINGS against the model, keep the body verbatim.
        write_result = edit_diagram(
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=clear_repo_caches,
            artifact_id=artifact_id,
            entity_ids_used=[e.artifact_id for e in entity_records],
            connection_ids_used=[c.artifact_id for c in conn_records],
            authored_groupings=authored_groupings,
            dry_run=dry_run,
        )
        return SyncDiagramToModelResult(
            wrote=write_result.wrote,
            path=write_result.path,
            artifact_id=write_result.artifact_id,
            content=write_result.content,
            warnings=[*write_result.warnings, *grouping_warnings, *staleness_warnings,
                      "manual-layout: body kept verbatim; bindings reconciled only"],
            verification=write_result.verification,
            removed_entity_ids=removed_entity_ids,
            removed_connection_ids=removed_conn_ids,
            deleted_diagram=False,
        )

    puml = generate_archimate_puml_body(
        name,
        entity_records,
        conn_records,
        diagram_type=diagram_type,
        edge_labels=existing_edge_labels,
        authored_groupings=authored_groupings or None,
    )

    write_result = edit_diagram(
        repo_root=repo_root,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        puml=puml,
        rebuild_layout=True,  # reconciling against the model is a deliberate rebuild of the picture
        entity_ids_used=[e.artifact_id for e in entity_records],
        connection_ids_used=[c.artifact_id for c in conn_records],
        authored_groupings=authored_groupings,
        dry_run=dry_run,
    )

    return SyncDiagramToModelResult(
        wrote=write_result.wrote,
        path=write_result.path,
        artifact_id=write_result.artifact_id,
        content=write_result.content,
        warnings=[*write_result.warnings, *grouping_warnings, *staleness_warnings],
        verification=write_result.verification,
        removed_entity_ids=removed_entity_ids,
        removed_connection_ids=removed_conn_ids,
        deleted_diagram=False,
    )
