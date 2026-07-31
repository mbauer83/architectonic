"""Fitness functions over the *shape* of the canonical addresses.

The rule these enforce: identity of the resource the operation addresses belongs in the path;
filters stay in the query; an action segment is the mark of an operation row and of nothing
else. Stated once here, over the manifest, rather than re-argued per router.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.gui.route_policy import (
    BODYLESS,
    LEGACY_ROUTES,
    MEDIA,
    MIGRATED_ROUTES,
    RETIRED_PATH_LITERALS,
    RETIRED_ROUTES,
    ROUTE_POLICY,
    STREAM,
    path_parameters,
)
from tests.support.retired_route_scan import find_retired_literals

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Action segments the manifest is allowed to spell, and the methods each may appear under.
#: Declared rather than inferred: a heuristic "is this word a verb" would either miss
#: ``cleanup-broken-refs`` or reject ``members``.
_ACTION_SEGMENTS: dict[str, frozenset[str]] = {
    "allocate": frozenset({"POST"}),
    "archive": frozenset({"POST"}),
    "cleanup-broken-refs": frozenset({"POST"}),
    "execute": frozenset({"POST"}),
    "execute-diagram": frozenset({"POST"}),
    "execute-projection": frozenset({"POST"}),
    "export": frozenset({"POST"}),
    "export-csv": frozenset({"POST"}),
    "export-render": frozenset({"POST"}),
    "model-this": frozenset({"POST"}),
    "plan": frozenset({"POST"}),
    "preview": frozenset({"POST"}),
    "reload": frozenset({"POST"}),
    "rename": frozenset({"POST"}),
    "save": frozenset({"POST"}),
    "submit": frozenset({"POST"}),
    "summarize": frozenset({"POST"}),
    "sync": frozenset({"POST"}),
    "unarchive": frozenset({"POST"}),
    "withdraw": frozenset({"POST"}),
}

#: Negative tests that must keep naming a retired route to prove it no longer resolves.
_RETIRED_LITERAL_EXEMPT_FILES: frozenset[Path] = frozenset()


def _final_literal_segment(template: str) -> str:
    segments = [s for s in template.split("/") if s and not (s.startswith("{") and s.endswith("}"))]
    return segments[-1] if segments else ""


def test_identity_of_a_resource_row_is_a_path_parameter() -> None:
    """A ``detail`` or ``subresource`` row addresses one resource, so its identity is in the
    path. Enforced at construction too; asserted here so the rule is visible as a rule."""
    for row in ROUTE_POLICY:
        if row.resource_kind in ("detail", "subresource"):
            assert row.identity_parameters, row.operation_id
            assert set(row.identity_parameters) == set(path_parameters(row.template)), row.operation_id


def test_action_segments_appear_only_on_operation_rows() -> None:
    """This replaces a blanket "no verb segment", which would contradict the operations
    exception the rule deliberately grants."""
    for row in ROUTE_POLICY:
        segment = _final_literal_segment(row.template)
        permitted_methods = _ACTION_SEGMENTS.get(segment)
        if permitted_methods is None:
            continue
        assert row.resource_kind == "operation", (
            f"{row.operation_id}: {segment!r} is an action segment, so the row is an operation"
        )
        assert row.method in permitted_methods, f"{row.operation_id}: {segment!r} under {row.method}"


def test_every_operation_row_names_its_action() -> None:
    """The converse: an operation row's template ends in a declared action segment, so a
    resource route cannot be classified as an operation to escape the identity rule."""
    for row in ROUTE_POLICY:
        if row.resource_kind != "operation":
            continue
        segment = _final_literal_segment(row.template)
        assert segment in _ACTION_SEGMENTS, f"{row.operation_id}: {segment!r} is not a declared action"


def test_no_canonical_template_repeats_a_collection_in_the_singular() -> None:
    """The defect this migration exists to remove: one router addressing an artifact by a query
    parameter for reads and by a path parameter for writes, under a singular collection name. A
    canonical collection is plural, so a singular sibling of a plural collection is a leftover."""
    plural_collections = {
        row.template
        for row in ROUTE_POLICY
        if row.resource_kind == "collection" and row.template.endswith("s")
    }
    for row in ROUTE_POLICY:
        head = "/".join(row.template.split("/")[:3])
        assert f"{head}s" not in plural_collections or head in plural_collections, (
            f"{row.operation_id}: {head!r} is the singular of a canonical plural collection"
        )


def test_every_declared_status_has_a_typed_body_or_is_explicitly_bodyless() -> None:
    """Phase 0's acceptance criterion, stated over the manifest: a row either names a DTO or
    declares itself bodyless, media or a stream. ``None`` is not an option."""
    for row in ROUTE_POLICY:
        assert row.response_contract, row.operation_id
        if row.response_contract in (BODYLESS, MEDIA, STREAM):
            continue
        assert row.response_contract[0].isupper(), row.operation_id


def test_bodyless_responses_are_deletions_or_idempotent_relation_assertions() -> None:
    """204 is a promise that there is nothing to say, which is true of a deletion and of a
    ``PUT`` that re-asserts a relation whose address is the request URL — and of nothing else."""
    for row in ROUTE_POLICY:
        if row.response_contract != BODYLESS:
            continue
        assert row.method in ("DELETE", "PUT"), row.operation_id


def test_migration_ledger_is_consistent() -> None:
    unknown = MIGRATED_ROUTES - frozenset(RETIRED_ROUTES)
    assert unknown == frozenset(), f"migrated keys absent from the retired record: {sorted(unknown)}"
    assert frozenset(LEGACY_ROUTES) == frozenset(RETIRED_ROUTES) - MIGRATED_ROUTES


def test_no_retired_route_literal_survives_in_the_working_tree() -> None:
    """Risk 15. Scoped to literals whose *every* method has moved: a collection path that still
    carries one unmigrated verb stays permitted until the last of them moves, because the literal
    is genuinely still served."""
    findings = find_retired_literals(
        _REPO_ROOT, RETIRED_PATH_LITERALS, exempt=_RETIRED_LITERAL_EXEMPT_FILES
    )
    assert findings == {}, "retired route literals still referenced:\n" + "\n".join(
        f"  {literal}: {', '.join(places)}" for literal, places in sorted(findings.items())
    )
