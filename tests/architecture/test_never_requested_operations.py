"""The set of REST operations nothing has ever requested may shrink and never grow.

Every other gate in this suite asks whether the code agrees with itself. This one asks whether the
*running application* has ever executed an operation, which is a different question and the one the
0.2.0 release got wrong: 73% of the write surface — including `POST /api/entities`, and all ten
`PATCH` routes the release had just moved to a new address and a new method — had never been reached
by a real request. Both of that release's worst defects were write-then-read paths, on two of the
few writes the browser suite happens to perform.

Two halves, with deliberately different reach:

* the manifest half runs anywhere, and catches a register entry stranded by a rename — the same
  spelling-in-two-places failure the addressing fitness functions exist for;
* the log half needs `.arch/backend.log`, which is deployment-local and gitignored. Where there is
  no log it skips *loudly*, because a check that passes on absent evidence is the green lie this
  whole register is a response to.
"""

from __future__ import annotations

import pytest

from src.infrastructure.rest.route_policy import BY_OPERATION, ROUTE_POLICY, RouteRow
from tools.quality.operation_execution import (
    NEVER_REQUESTED_OPERATIONS,
    RequestedRoute,
    never_requested_operations,
    operation_for,
    parse_requested_routes,
    read_request_log,
    requested_operations,
)

_FIXTURE_ROWS: tuple[RouteRow, ...] = (
    RouteRow("GET", "/api/things", "collection", "things_list_things", "typed"),
    RouteRow("POST", "/api/things", "collection", "things_create_thing", "typed"),
    RouteRow(
        "GET", "/api/things/{thing_id}", "detail", "things_read_thing", "typed",
        identity_parameters=("thing_id",),
    ),
    RouteRow("GET", "/api/things/pinned", "catalog", "things_list_pinned_things", "typed"),
    RouteRow(
        "PATCH", "/api/things/{thing_id}", "detail", "things_update_thing", "typed",
        identity_parameters=("thing_id",),
    ),
)


def test_every_registered_operation_is_a_declared_one() -> None:
    stranded = sorted(NEVER_REQUESTED_OPERATIONS - set(BY_OPERATION))
    assert stranded == [], (
        "These register entries name operations the manifest does not declare — a rename moved the "
        f"operation and left its register entry behind: {stranded}"
    )


def test_the_register_never_claims_a_read_that_the_client_obviously_drives() -> None:
    # A guard on the guard: were the matcher to stop resolving anything, every operation would look
    # dark and the register would have been populated with all 166. These four are on the first
    # screen the GUI loads, so their presence would mean the measurement, not the product, is broken.
    always_driven = {
        "entities_list_entities",
        "connections_list_connections",
        "diagrams_list_diagrams",
        "taxonomy_read_repository_stats",
    }
    declared = always_driven & set(BY_OPERATION)
    assert declared == always_driven, (
        f"these sentinels are no longer declared — pick new ones: {sorted(always_driven - declared)}"
    )
    assert declared - NEVER_REQUESTED_OPERATIONS == declared


def test_a_concrete_path_resolves_to_the_operation_that_served_it() -> None:
    assert operation_for(RequestedRoute("GET", "/api/things"), _FIXTURE_ROWS) == "things_list_things"
    assert (
        operation_for(RequestedRoute("POST", "/api/things"), _FIXTURE_ROWS)
        == "things_create_thing"
    )
    assert (
        operation_for(RequestedRoute("GET", "/api/things/ENT@1.abc"), _FIXTURE_ROWS)
        == "things_read_thing"
    )
    assert (
        operation_for(RequestedRoute("PATCH", "/api/things/ENT@1.abc"), _FIXTURE_ROWS)
        == "things_update_thing"
    )


def test_a_literal_segment_wins_over_a_parameter_that_would_also_match() -> None:
    # The server registers `/api/things/pinned` first and matches it first, so a request for it ran
    # the pin list — never a thing whose id is "pinned".
    assert (
        operation_for(RequestedRoute("GET", "/api/things/pinned"), _FIXTURE_ROWS)
        == "things_list_pinned_things"
    )


def test_an_address_the_manifest_does_not_serve_resolves_to_nothing() -> None:
    assert operation_for(RequestedRoute("GET", "/api/thing?id=x"), _FIXTURE_ROWS) is None
    assert operation_for(RequestedRoute("DELETE", "/api/things/ENT@1.abc"), _FIXTURE_ROWS) is None
    assert operation_for(RequestedRoute("GET", "/api/things/a/b"), _FIXTURE_ROWS) is None


def test_the_query_string_is_not_part_of_the_address() -> None:
    routes = parse_requested_routes('127.0.0.1 - "GET /api/things?limit=10 HTTP/1.1" 200')
    assert routes == frozenset({RequestedRoute("GET", "/api/things")})
    assert requested_operations(routes, _FIXTURE_ROWS) == frozenset({"things_list_things"})


def test_a_log_with_no_request_lines_leaves_every_operation_dark() -> None:
    quiet = "2026-08-02 08:36:00,000 INFO src.infrastructure.backend: started\n"
    assert never_requested_operations(parse_requested_routes(quiet), _FIXTURE_ROWS) == frozenset(
        row.operation_id for row in _FIXTURE_ROWS
    )


def _measured_dark_operations() -> frozenset[str]:
    log_text = read_request_log()
    if log_text is None:
        pytest.skip(
            "no .arch/backend.log — the register's log half is unmeasurable here. Run "
            "`uv run tools/quality/never_requested_operations.py` where a backend has served."
        )
    return never_requested_operations(parse_requested_routes(log_text))


def test_no_operation_outside_the_register_is_dark() -> None:
    grown = sorted(_measured_dark_operations() - NEVER_REQUESTED_OPERATIONS)
    assert grown == [], (
        "These operations are served and nothing has ever requested one. Drive each through the "
        "running server — the conformance harness, the browser suite or a CLI round trip — rather "
        f"than adding it to the register, which only shrinks: {grown}"
    )


def test_the_register_holds_nothing_that_has_since_been_requested() -> None:
    covered = sorted(NEVER_REQUESTED_OPERATIONS - _measured_dark_operations())
    assert covered == [], (
        "These have been requested since the register was taken. Remove them from "
        f"NEVER_REQUESTED_OPERATIONS: {covered}"
    )


def test_the_register_is_a_minority_of_the_surface_and_says_which_part() -> None:
    # The register is evidence, so it has to stay legible as evidence: it is worth knowing at a
    # glance that it covers the write surface and barely touches reads.
    assert len(NEVER_REQUESTED_OPERATIONS) < len(ROUTE_POLICY) / 2
    dark_writes = sum(1 for op in NEVER_REQUESTED_OPERATIONS if BY_OPERATION[op].is_write_shaped)
    assert dark_writes > len(NEVER_REQUESTED_OPERATIONS) / 2
