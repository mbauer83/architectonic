"""The set of REST operations nothing has requested, in the log's window, may shrink and never grow.

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

The two halves of the *log* check need different amounts of evidence, and conflating them was a real
hole. That a registered operation has since been requested is **positive** evidence and needs no
history at all. That an *unregistered* operation is dark is a claim about a period, and a log that
begins after the register was taken cannot support it — a freshly rotated log would otherwise report
sixty dark operations from ten minutes of history. So that half runs only where the log predates
`REGISTER_TAKEN`, and says which it is rather than passing quietly.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.infrastructure.rest.route_policy import BY_OPERATION, ROUTE_POLICY, RouteRow
from tools.quality.operation_execution import (
    NEVER_REQUESTED_OPERATIONS,
    REGISTER_TAKEN,
    RequestedRoute,
    covers_the_register,
    log_begins_at,
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


def test_only_a_successful_request_counts_as_having_exercised_an_operation() -> None:
    """A 400 means the validator ran, not the handler. Counting a rejection as evidence is how a
    register like this quietly empties: every operation has been *asked for* at some point."""
    rejected = '"POST /api/things HTTP/1.1" 400\n"GET /api/things/x HTTP/1.1" 404\n'
    assert parse_requested_routes(rejected) == frozenset()
    accepted = '"POST /api/things HTTP/1.1" 201\n"GET /api/things/x HTTP/1.1" 200\n'
    assert requested_operations(parse_requested_routes(accepted), _FIXTURE_ROWS) == frozenset(
        {"things_create_thing", "things_read_thing"}
    )
    # 204 counts: a deletion has no body and says so with a status, which is still the handler
    # having done its work.
    assert parse_requested_routes('"GET /api/things HTTP/1.1" 204') != frozenset()


def test_a_log_with_no_request_lines_leaves_every_operation_dark() -> None:
    quiet = "2026-08-02 08:36:00,000 INFO src.infrastructure.backend: started\n"
    assert never_requested_operations(parse_requested_routes(quiet), _FIXTURE_ROWS) == frozenset(
        row.operation_id for row in _FIXTURE_ROWS
    )


def _log_text_or_skip() -> str:
    log_text = read_request_log()
    if log_text is None:
        pytest.skip(
            "no .arch/backend.log — the register's log half is unmeasurable here. Run "
            "`uv run tools/quality/never_requested_operations.py` where a backend has served."
        )
    return log_text


def _walked_by_the_write_walk() -> frozenset[str]:
    """Operations the REST write walk requests every run, against its own fixture backend.

    Subtracted from what this log shows, because coverage stopped coming from one process. The walk
    serves a disposable workspace on its own port and writes its access log there, so `.arch/backend.log`
    — the dogfood backend's — cannot contain those requests however many times the walk has run.

    Reading the step tuples is a *claim*; the evidence is `tests/tools/test_rest_write_walk.py`, which
    runs both walks and asserts every step appears in that backend's own log. So the two halves are
    separate and both in this suite: a step that stops being requested fails there, not silently here.

    Both tuples, because the enterprise surface needs a backend in a different *mode* and therefore a
    second sequential run — a second log this one cannot contain either.
    """
    from tools.quality.rest_write_walk import ADMIN_STEPS, STEPS

    return frozenset(step.operation_id for step in (*STEPS, *ADMIN_STEPS))


def _measured_dark_operations() -> frozenset[str]:
    dark = never_requested_operations(parse_requested_routes(_log_text_or_skip()), ROUTE_POLICY)
    return dark - _walked_by_the_write_walk()


def test_no_operation_outside_the_register_is_dark() -> None:
    log_text = _log_text_or_skip()
    if not covers_the_register(log_text):
        pytest.skip(
            f"the log begins at {log_begins_at(log_text)}, after the register was taken at "
            f"{REGISTER_TAKEN} — it cannot show what was requested before it started, so absence in "
            "it is not evidence. Re-take the register: "
            "`uv run tools/quality/never_requested_operations.py`."
        )
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
    """The register is evidence, so it has to stay legible as evidence.

    This used to assert that dark *writes* outnumbered dark reads — "it is worth knowing at a glance
    that it covers the write surface and barely touches reads". That was a description of the register's
    composition on the day it was written, encoded as an invariant, and it inverted the moment the write
    surface actually got covered: 24 write-shaped against 26 read-shaped. A gate that fails because the
    work it measures succeeded is a gate that forbids finishing, so the assertion is now the property
    that was wanted underneath it.
    """
    assert len(NEVER_REQUESTED_OPERATIONS) < len(ROUTE_POLICY) / 2

    # Which part it covers, stated as a claim that survives progress: the write surface is dark only
    # where a precondition is *recorded*. Every write-shaped entry belongs to a family the write walk
    # registers in `UNWALKED` with a reason, so a newly dark write cannot hide among the ones that are
    # dark on purpose — and when those slices land this narrows to nothing rather than needing an edit.
    from tools.quality.rest_write_walk import UNWALKED

    excused = {key.split("/", 1)[0] for key in UNWALKED}
    unexcused = sorted(
        operation
        for operation in NEVER_REQUESTED_OPERATIONS
        if BY_OPERATION[operation].is_write_shaped and operation.split("_", 1)[0] not in excused
    )
    assert unexcused == [], (
        "these write operations are dark and no precondition in the write walk's UNWALKED register "
        f"accounts for them: {unexcused}"
    )


def test_a_log_that_begins_after_the_register_cannot_prove_an_operation_is_dark() -> None:
    """The coverage rule, on fixtures this test owns.

    Positive evidence needs no history; the negative claim does. A log rotated ten minutes ago would
    otherwise report every operation as dark with complete confidence — which is how deleting 45 MB
    of history turned this module from a measurement into an assertion about nothing.
    """
    taken = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
    before = '2026-08-02 11:00:00,000 INFO started\n"GET /api/things HTTP/1.1" 200\n'
    after = '2026-08-02 12:30:00,000 INFO started\n"GET /api/things HTTP/1.1" 200\n'

    assert covers_the_register(before, taken) is True
    assert covers_the_register(after, taken) is False
    # No timestamp at all is not coverage either: a log whose format changed would otherwise read as
    # spanning all of history.
    assert covers_the_register('"GET /api/things HTTP/1.1" 200', taken) is False


def test_the_log_window_is_read_from_the_log_rather_than_assumed() -> None:
    assert log_begins_at("2026-08-02 11:00:00,000 INFO started\n") == datetime(
        2026, 8, 2, 11, 0, tzinfo=UTC
    )
    assert log_begins_at("no timestamps here") is None


def test_the_write_walk_subtraction_names_only_declared_operations() -> None:
    """Guards the subtraction: an operation id that is not in the manifest would silently exempt nothing
    while looking like it exempted something, and a typo is exactly how that happens."""
    from src.infrastructure.rest.route_policy import BY_OPERATION

    unknown = sorted(_walked_by_the_write_walk() - set(BY_OPERATION))
    assert unknown == [], f"the write walk names operations the manifest does not declare: {unknown}"


def test_the_write_walk_covers_only_write_shaped_operations() -> None:
    """A walk that started subtracting GETs would be hiding read coverage behind a write fixture, which
    is the kind of quiet reclassification this register exists to prevent."""
    from src.infrastructure.rest.route_policy import BY_OPERATION

    reads = sorted(op for op in _walked_by_the_write_walk() if BY_OPERATION[op].method == "GET")
    assert reads == [], f"the write walk subtracts read operations: {reads}"
