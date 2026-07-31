"""Fitness functions over the REST route-policy manifest.

These are the tests that make the manifest a specification rather than documentation. Each one
compares the manifest against an oracle it does not produce — the generated OpenAPI document,
the mutation-authorization manifest, the conditional-read allowlist — so agreement is evidence
and not a tautology.

The two allowlists in ``route_policy._pending`` are what let these be *equalities* while the
migration is in progress. They shrink monotonically and are empty when it is done; the tests
below refuse a stale entry in either direction, so neither can quietly outlive its purpose.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.infrastructure.gui.route_policy import (
    BY_OPERATION,
    CONDITIONAL_READ_TEMPLATES,
    LEGACY_ROUTES,
    ROUTE_POLICY,
    UNSERVED_OPERATIONS,
    served_templates_for,
)
from src.infrastructure.gui.routers.rest_mutation_manifest import (
    ASSURANCE_ROUTE_PREFIX,
    NON_MUTATING_REST_OPERATIONS,
    REST_MUTATION_MANIFEST,
)
from tests.support.route_policy_inventory import effective_route_keys, served_route_keys

#: The repository root, for the few checks that read a client-side source file.
_REPO_ROOT = Path(__file__).resolve().parents[2]

def _operations(*, mutation_domain: str, under_assurance: bool | None = None) -> set[str]:
    """Operation ids in one mutation domain, optionally scoped to (or away from) assurance."""
    return {
        row.operation_id
        for row in ROUTE_POLICY
        if row.mutation_domain == mutation_domain
        and (
            under_assurance is None
            or row.template.startswith(ASSURANCE_ROUTE_PREFIX) is under_assurance
        )
    }

_TAGS = frozenset({
    "admin", "assurance", "connections", "diagrams", "documents", "entities", "events",
    "groups", "matrices", "promotion", "sync", "taxonomy", "viewpoints",
})

_OPERATION_ID_RE = re.compile(r"^(?P<tag>[a-z]+)_(?P<verb>[a-z]+)_(?P<resource>[a-z0-9_]+)$")


@pytest.fixture(scope="module")
def served() -> frozenset[tuple[str, str]]:
    return served_route_keys()


def test_every_operation_id_is_tag_verb_resource() -> None:
    """``openapi-typescript`` keys its generated types by operation id, so the id is part of
    the published contract and has to be stable and derivable — not FastAPI's default
    function-name-plus-mangled-path."""
    for row in ROUTE_POLICY:
        match = _OPERATION_ID_RE.match(row.operation_id)
        assert match is not None, f"{row.operation_id!r} is not {{tag}}_{{verb}}_{{resource}}"
        assert match.group("tag") in _TAGS, f"{row.operation_id!r} has an unknown tag"


def test_served_surface_is_exactly_the_manifest_plus_the_legacy_allowlist(
    served: frozenset[tuple[str, str]],
) -> None:
    """The inventory equality: nothing is served that the manifest has not classified, and
    nothing the manifest declares is missing — legacy addresses accounted for explicitly."""
    expected = frozenset(key for row in ROUTE_POLICY for key in effective_route_keys(row))
    assert served - expected == frozenset(), "served but unclassified"
    assert expected - served == frozenset(), "classified but not served"


def test_legacy_allowlist_names_only_declared_operations() -> None:
    unknown = {op for op in LEGACY_ROUTES.values() if op not in BY_OPERATION}
    assert unknown == set(), f"legacy rows point at undeclared operations: {sorted(unknown)}"


def test_legacy_allowlist_shrinks_only(served: frozenset[tuple[str, str]]) -> None:
    """A legacy entry whose route is no longer served has been migrated; the entry has to go
    in the same commit, or the allowlist stops measuring what is left."""
    stale = set(LEGACY_ROUTES) - served
    assert stale == set(), f"legacy allowlist entries no longer served: {sorted(stale)}"


def test_unserved_operations_are_declared_and_genuinely_unserved(
    served: frozenset[tuple[str, str]],
) -> None:
    undeclared = {op for op in UNSERVED_OPERATIONS if op not in BY_OPERATION}
    assert undeclared == set(), f"unserved allowlist names undeclared operations: {sorted(undeclared)}"
    already = {op for op in UNSERVED_OPERATIONS if BY_OPERATION[op].key in served}
    assert already == set(), f"listed as unserved but mounted: {sorted(already)}"


def test_repository_mutating_rows_match_the_mutation_authorization_manifest() -> None:
    """Fitness equation 1: repository-mutating rows ≡ ``REST_MUTATION_MANIFEST`` keys.

    ``/api/assurance`` is deliberately outside that manifest — the confidential store owns its
    own unlock gating — which is why this is scoped by ``mutation_domain`` rather than being one
    global equality over every write-shaped route.

    Compared by operation id, because that is what both registries are now keyed by: an
    authorization identity that moved when a path moved was the defect this replaced."""
    assert _operations(mutation_domain="repository", under_assurance=False) == set(
        REST_MUTATION_MANIFEST
    )


def test_no_repository_mutator_lives_under_the_assurance_prefix() -> None:
    """The exclusion above is only sound while it excludes nothing: a route under
    ``/api/assurance`` that mutated the architecture repository would escape both gates."""
    assert _operations(mutation_domain="repository", under_assurance=True) == set()


def test_non_mutating_write_shaped_rows_match_the_declared_non_mutating_set() -> None:
    """Fitness equation 3: a write-shaped route that mutates nothing is declared as such in
    both places, so neither can quietly start counting as a mutator.

    Scoped the same way as equation 1 — the assurance surface's non-mutating write-shaped
    operations are declared in the route-policy manifest alone, since the architecture
    mutation manifest excludes that prefix."""
    write_shaped = {
        row.operation_id
        for row in ROUTE_POLICY
        if row.is_write_shaped
        and row.mutation_domain == "none"
        and not row.template.startswith(ASSURANCE_ROUTE_PREFIX)
    }
    assert write_shaped == NON_MUTATING_REST_OPERATIONS


def test_assurance_responses_are_never_stored_or_revalidated() -> None:
    """A direct read of an above-ceiling id must stay indistinguishable from a read of an
    absent one. ``no-store`` is what keeps the body out of a cache; the absence of an ETag is
    what keeps the *existence* of the body out of a validator."""
    for row in ROUTE_POLICY:
        if row.template.startswith("/api/assurance"):
            assert row.cache_directive == "no-store", row.operation_id
            assert row.conditional_read == "none", row.operation_id


def test_no_mutation_is_conditionally_readable() -> None:
    for row in ROUTE_POLICY:
        if row.is_write_shaped:
            assert row.conditional_read == "none", row.operation_id


def test_the_middleware_recognises_exactly_the_cache_eligible_reads(
    served: frozenset[tuple[str, str]],
) -> None:
    """Fitness: the matcher agrees with the manifest over the whole *served* surface.

    Not an equality between the manifest and a copy of itself — the middleware now derives its
    set from the manifest, so comparing the two would be a tautology. What can still be wrong is
    the *matching*: an unanchored or over-broad template pattern would adopt routes nobody
    classified. So every served GET is checked both ways against an independent oracle, the
    generated OpenAPI document."""
    from src.infrastructure.backend.read_model_caching import _is_cacheable

    eligible = frozenset(
        template
        for row in ROUTE_POLICY
        if row.conditional_read == "etag"
        for template in served_templates_for(row.operation_id)
    )
    for method, template in sorted(served):
        if method != "GET":
            continue
        concrete = re.sub(r"\{[^}]+\}", "PLACEHOLDER", template)
        assert _is_cacheable(concrete) is (template in eligible), f"{method} {template}"


def test_conditional_read_templates_are_all_get_reads() -> None:
    for template in CONDITIONAL_READ_TEMPLATES:
        rows = [row for row in ROUTE_POLICY if row.template == template and row.conditional_read == "etag"]
        assert all(row.method == "GET" for row in rows), template


def test_the_client_analysis_method_vocabulary_matches_the_domain() -> None:
    """The GUI's method list is the domain's, not a copy that drifts.

    The picker's list decides which methods a user can choose and filter for. It omitted ``FMEA``
    while the domain accepted it, so an FMEA analysis could be created through the API and then not
    be selectable in the surface whose whole job is to project one. Scanned from the source rather
    than generated, because the list is three lines and a generator would be the larger risk.
    """
    from src.domain.assurance.assurance_analysis import ANALYSIS_METHODS

    source = (
        _REPO_ROOT / "tools/gui/src/ui/components/AssuranceAnalysisPicker.helpers.ts"
    ).read_text(encoding="utf-8")
    match = re.search(r"export const ANALYSIS_METHODS = \[(.*?)\] as const", source, re.S)
    assert match is not None, "the picker no longer declares ANALYSIS_METHODS"
    declared = tuple(name.strip().strip("'\"") for name in match.group(1).split(",") if name.strip())

    assert declared == tuple(ANALYSIS_METHODS), (
        "the GUI's analysis methods differ from the domain's: "
        f"{declared} vs {tuple(ANALYSIS_METHODS)}"
    )
