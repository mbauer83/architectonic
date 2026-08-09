"""Fitness functions over the *shape* of the canonical addresses.

The rule these enforce: identity of the resource the operation addresses belongs in the path;
filters stay in the query; an action segment is the mark of an operation row and of nothing
else. Stated once here, over the manifest, rather than re-argued per router.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.infrastructure.rest.route_policy import (
    BODYLESS,
    RESPONSE_KINDS,
    RETIRED_PATH_LITERALS,
    RETIRED_ROUTES,
    ROUTE_POLICY,
    path_parameters,
)
from tests.support.retired_route_scan import (
    find_retired_literals,
    find_retired_method_calls,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    """The served surface, from the application object — not `app.routes`, which sees 13 of 161."""
    from src.infrastructure.backend.arch_backend_app import _build_app

    return _build_app().openapi()

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
    "lift": frozenset({"POST"}),
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


def test_every_row_declares_a_response_kind_and_a_bodyless_row_is_a_mutation() -> None:
    """The kind is declared, and ``bodyless`` is reserved for what genuinely has nothing to say.

    This used to assert the column held a DTO *name* — that it was capitalised, that a bodyless row
    was not a GET. The name is gone: it pointed at a shape defined in ``contracts/``, and a pointer to
    a class that did not exist was a work item wearing the costume of a decision. What is left is
    checkable without naming anything.
    """
    for row in ROUTE_POLICY:
        assert row.response_kind in RESPONSE_KINDS, f"{row.operation_id}: {row.response_kind!r}"
        if row.response_kind == BODYLESS:
            assert row.method != "GET", (
                f"{row.operation_id}: a read with nothing to return is a read nobody needs"
            )

def test_bodyless_responses_are_deletions_or_idempotent_relation_assertions() -> None:
    """204 is a promise that there is nothing to say, which is true of a deletion and of a
    ``PUT`` that re-asserts a relation whose address is the request URL — and of nothing else."""
    for row in ROUTE_POLICY:
        if row.response_kind != BODYLESS:
            continue
        assert row.method in ("DELETE", "PUT"), row.operation_id


def test_no_retired_address_is_still_served(document: dict[str, Any]) -> None:
    """The statement the migration ledger used to make in two halves, made directly.

    Two collections tracked which retired addresses were still mounted and which canonical ones were
    not mounted yet, and a fitness function compared them for consistency. Both reached their end
    state, at which point the ledger asserted only that it agreed with itself. What actually matters
    is this: nothing answers at an address 0.2.0 retired. Asked of the served document, so it cannot
    be satisfied by bookkeeping.
    """
    served = {
        (method.upper(), path)
        for path, methods in document.get("paths", {}).items()
        for method in methods
    }
    still_served = sorted(key for key in RETIRED_ROUTES if key in served)
    assert still_served == [], f"retired addresses still mounted: {still_served}"


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


def test_no_client_still_calls_a_retired_method_on_a_live_path() -> None:
    """The gap the test above cannot see, and it cost a 405 in the browser.

    A path stays permitted while any method on it is still mounted — right for paths, blind to
    verbs. ``POST /api/assurance/nodes`` was retired while ``GET /api/assurance/nodes`` stayed, so
    four GUI callers went on posting to it and the only thing that noticed was an e2e run. The
    served surface answers 405, which no unit test exercises and no path scan reports.
    """
    live_paths = frozenset(
        template for _method, template in RETIRED_ROUTES
        if template not in RETIRED_PATH_LITERALS
    )
    findings = find_retired_method_calls(
        _REPO_ROOT, RETIRED_ROUTES, live_paths=live_paths,
        exempt=_RETIRED_LITERAL_EXEMPT_FILES,
    )
    assert findings == {}, (
        "clients still using a retired method on a path that is live for other methods:\n"
        + "\n".join(f"  {pair}: {', '.join(places)}" for pair, places in sorted(findings.items()))
    )