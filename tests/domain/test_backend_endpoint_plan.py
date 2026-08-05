"""Endpoint planning: which backend a workspace may use, and where it may start one.

The states a machine can be in are enumerated here rather than staged with real sockets: nothing
running, our own backend up (on the preferred port, on a derived one, at a recorded one), a
neighbour's backend holding the default, a non-backend process holding it, a backend that will not
say what it serves, a stale record, a declared port taken, and an exhausted range.

The failure these guard against is silent: a bridge that attaches to a foreign backend answers every
call correctly, about the wrong model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.deployment.backend_endpoint import (
    DERIVED_PORT_CEILING,
    DERIVED_PORT_FLOOR,
    AttachToBackend,
    BackendIdentity,
    EndpointObservation,
    PortPreference,
    RefuseEndpoint,
    StartBackendOn,
    WorkspaceClaim,
    classify_endpoint,
    derived_port,
    derived_port_sequence,
    endpoint_candidates,
    plan_endpoint,
)

OURS = WorkspaceClaim(engagement_root=Path("/w/one/engagement"), enterprise_root=Path("/w/one/enterprise"))
NEIGHBOUR = WorkspaceClaim(engagement_root=Path("/w/two/engagement"), enterprise_root=Path("/w/two/enterprise"))
DEFAULT = PortPreference(port=8000, authority="settings_document")
DECLARED = PortPreference(port=8000, authority="workspace_config")
COMMANDED = PortPreference(port=8000, authority="command")


def _identity(claim: WorkspaceClaim, *, version: str = "9.9.9") -> BackendIdentity:
    roots = [str(claim.engagement_root)] + ([str(claim.enterprise_root)] if claim.enterprise_root else [])
    return BackendIdentity(repo_roots=tuple(roots), software_version=version)


def _free(port: int) -> EndpointObservation:
    return EndpointObservation(port=port, socket_taken=False, answers_probe=False)


def _serving(port: int, claim: WorkspaceClaim) -> EndpointObservation:
    return EndpointObservation(port=port, socket_taken=True, answers_probe=True, identity=_identity(claim))


def _silent_occupant(port: int) -> EndpointObservation:
    """Something holds the socket but answers no probe — another service, or a wedged backend."""
    return EndpointObservation(port=port, socket_taken=True, answers_probe=False)


def _anonymous(port: int) -> EndpointObservation:
    """Answers the liveness probe but reports no identity — an older backend, or an unrelated app."""
    return EndpointObservation(port=port, socket_taken=True, answers_probe=True, identity=None)


def _world(**by_port: EndpointObservation):
    """An observer over a fixed machine state; unlisted ports are free."""
    calls: list[int] = []

    def observe(port: int) -> EndpointObservation:
        calls.append(port)
        return by_port.get(str(port), _free(port))

    observe.calls = calls  # type: ignore[attr-defined]
    return observe


def _plan(observe, *, claim=OURS, preference=DEFAULT, recorded_port=None, may_start=True):
    return plan_endpoint(
        claim=claim,
        preference=preference,
        recorded_port=recorded_port,
        may_start=may_start,
        observe=observe,
    )


# ── Classification ────────────────────────────────────────────────────────────


def test_a_backend_serving_our_roots_is_ours() -> None:
    assert classify_endpoint(_serving(8000, OURS), OURS) == "ours"


def test_a_backend_serving_other_roots_is_foreign() -> None:
    assert classify_endpoint(_serving(8000, NEIGHBOUR), OURS) == "foreign"


def test_our_engagement_under_a_different_enterprise_tier_is_a_conflict() -> None:
    mixed = EndpointObservation(
        port=8000,
        socket_taken=True,
        answers_probe=True,
        identity=BackendIdentity(
            repo_roots=(str(OURS.engagement_root), str(NEIGHBOUR.enterprise_root)),
            software_version="9.9.9",
        ),
    )

    assert classify_endpoint(mixed, OURS) == "enterprise_conflict"


def test_an_engagement_only_claim_ignores_the_enterprise_tier() -> None:
    engagement_only = WorkspaceClaim(engagement_root=OURS.engagement_root)

    assert classify_endpoint(_serving(8000, OURS), engagement_only) == "ours"


def test_a_workspace_without_a_claim_can_never_recognise_its_own_backend() -> None:
    assert classify_endpoint(_serving(8000, OURS), None) == "unidentified"


def test_a_backend_reporting_no_roots_is_evidence_of_nothing() -> None:
    starting_up = EndpointObservation(
        port=8000,
        socket_taken=True,
        answers_probe=True,
        identity=BackendIdentity(repo_roots=(), software_version="9.9.9"),
    )

    assert classify_endpoint(starting_up, OURS) == "unidentified"


def test_a_bound_socket_that_never_answers_is_occupied() -> None:
    assert classify_endpoint(_silent_occupant(8000), OURS) == "occupied"


def test_an_untouched_port_is_free() -> None:
    assert classify_endpoint(_free(8000), OURS) == "free"


# ── Derived ports ─────────────────────────────────────────────────────────────


def test_a_workspace_derives_the_same_port_every_time() -> None:
    assert derived_port(OURS.fingerprint) == derived_port(OURS.fingerprint)


def test_different_workspaces_derive_different_ports() -> None:
    assert derived_port(OURS.fingerprint) != derived_port(NEIGHBOUR.fingerprint)


def test_derived_ports_stay_inside_the_reserved_range() -> None:
    for claim in (OURS, NEIGHBOUR, WorkspaceClaim(engagement_root=Path("/w/three"))):
        assert DERIVED_PORT_FLOOR <= derived_port(claim.fingerprint) <= DERIVED_PORT_CEILING


def test_the_derived_sequence_is_distinct_and_bounded() -> None:
    sequence = derived_port_sequence(OURS.fingerprint, attempts=5)

    assert len(set(sequence)) == 5
    assert all(DERIVED_PORT_FLOOR <= port <= DERIVED_PORT_CEILING for port in sequence)


def test_workspaces_serving_the_same_repositories_are_one_instance() -> None:
    same_roots = WorkspaceClaim(engagement_root=OURS.engagement_root, enterprise_root=OURS.enterprise_root)

    assert same_roots.fingerprint == OURS.fingerprint


def test_the_recorded_port_is_examined_before_the_preferred_one() -> None:
    candidates = endpoint_candidates(preference=DEFAULT, claim=OURS, recorded_port=8137)

    assert candidates[0] == 8137
    assert candidates[1] == 8000


def test_a_stated_port_brings_no_derived_candidates() -> None:
    """A port that will not be moved off makes "where else could we go" an unusable answer.

    It is also not free to ask: every candidate is a connection attempt against a machine that may
    not refuse promptly — nine of them once outlasted the deadline the caller was waiting under.
    """
    candidates = endpoint_candidates(preference=DECLARED, claim=OURS, recorded_port=8137)

    assert candidates == (8137, DECLARED.port)


def test_candidates_never_repeat_a_port() -> None:
    candidates = endpoint_candidates(preference=DEFAULT, claim=OURS, recorded_port=8000)

    assert len(candidates) == len(set(candidates))


# ── Planning: an empty machine ────────────────────────────────────────────────


def test_nothing_running_starts_on_the_preferred_port() -> None:
    assert _plan(_world()) == StartBackendOn(port=8000)


def test_nothing_running_and_no_autostart_refuses_with_the_engagement_root() -> None:
    plan = _plan(_world(), may_start=False)

    assert isinstance(plan, RefuseEndpoint)
    assert "is not running" in plan.reason
    assert str(OURS.engagement_root) in plan.reason


# ── Planning: our own backend ─────────────────────────────────────────────────


def test_our_backend_on_the_preferred_port_is_reused() -> None:
    plan = _plan(_world(**{"8000": _serving(8000, OURS)}))

    assert plan == AttachToBackend(port=8000, identity=_identity(OURS))


def test_our_backend_at_the_recorded_port_is_reused_even_when_the_default_is_busy() -> None:
    observe = _world(**{"8000": _serving(8000, NEIGHBOUR), "8137": _serving(8137, OURS)})

    plan = _plan(observe, recorded_port=8137)

    assert isinstance(plan, AttachToBackend)
    assert plan.port == 8137


def test_our_backend_on_a_derived_port_is_found_without_a_record() -> None:
    own_port = derived_port(OURS.fingerprint)
    observe = _world(**{"8000": _serving(8000, NEIGHBOUR), str(own_port): _serving(own_port, OURS)})

    plan = _plan(observe)

    assert plan == AttachToBackend(port=own_port, identity=_identity(OURS))


def test_a_stale_record_pointing_at_nothing_is_ignored() -> None:
    plan = _plan(_world(), recorded_port=8137)

    assert plan == StartBackendOn(port=8000)


def test_a_record_whose_port_a_neighbour_took_never_attaches() -> None:
    observe = _world(**{"8137": _serving(8137, NEIGHBOUR)})

    plan = _plan(observe, recorded_port=8137)

    assert plan == StartBackendOn(port=8000)


# ── Planning: a neighbour holds the default port ───────────────────────────────


def test_a_neighbour_on_the_default_port_moves_us_to_our_own() -> None:
    observe = _world(**{"8000": _serving(8000, NEIGHBOUR)})

    plan = _plan(observe)

    assert plan == StartBackendOn(
        port=derived_port(OURS.fingerprint), moved_from=8000, moved_because="foreign"
    )


def test_a_neighbour_on_the_default_port_never_yields_an_attachment() -> None:
    observe = _world(**{"8000": _serving(8000, NEIGHBOUR)})

    plan = _plan(observe, may_start=False)

    assert isinstance(plan, RefuseEndpoint)
    assert str(NEIGHBOUR.engagement_root) in plan.reason


def test_an_unrelated_service_on_the_default_port_moves_us_too() -> None:
    plan = _plan(_world(**{"8000": _silent_occupant(8000)}))

    assert isinstance(plan, StartBackendOn)
    assert plan.moved_because == "occupied"
    assert plan.port != 8000


def test_a_backend_that_will_not_identify_itself_is_not_treated_as_ours() -> None:
    plan = _plan(_world(**{"8000": _anonymous(8000)}))

    assert isinstance(plan, StartBackendOn)
    assert plan.port != 8000


def test_the_next_derived_port_is_used_when_the_first_is_taken() -> None:
    first, second = derived_port_sequence(OURS.fingerprint)[:2]
    observe = _world(**{
        "8000": _serving(8000, NEIGHBOUR),
        str(first): _silent_occupant(first),
    })

    plan = _plan(observe)

    assert isinstance(plan, StartBackendOn)
    assert plan.port == second


def test_an_exhausted_range_refuses_instead_of_scanning_on() -> None:
    taken = {str(port): _silent_occupant(port) for port in derived_port_sequence(OURS.fingerprint)}
    taken["8000"] = _serving(8000, NEIGHBOUR)

    plan = _plan(_world(**taken))

    assert isinstance(plan, RefuseEndpoint)
    assert "No free port" in plan.reason


# ── Planning: a stated port is obeyed or refused, never moved ──────────────────


@pytest.mark.parametrize("preference", [DECLARED, COMMANDED])
def test_a_stated_port_taken_by_a_neighbour_refuses(preference: PortPreference) -> None:
    plan = _plan(_world(**{"8000": _serving(8000, NEIGHBOUR)}), preference=preference)

    assert isinstance(plan, RefuseEndpoint)
    assert "8000" in plan.reason
    assert str(NEIGHBOUR.engagement_root) in plan.reason


def test_a_commanded_port_names_the_flag_that_set_it() -> None:
    plan = _plan(_world(**{"8000": _silent_occupant(8000)}), preference=COMMANDED)

    assert isinstance(plan, RefuseEndpoint)
    assert "--port" in plan.reason


def test_a_workspace_declared_port_names_the_workspace_file() -> None:
    plan = _plan(_world(**{"8000": _silent_occupant(8000)}), preference=DECLARED)

    assert isinstance(plan, RefuseEndpoint)
    assert "arch-workspace.yaml" in plan.reason


def test_a_stated_port_that_is_free_is_used() -> None:
    assert _plan(_world(), preference=DECLARED) == StartBackendOn(port=8000)


def test_our_own_backend_on_a_stated_port_is_still_reused() -> None:
    plan = _plan(_world(**{"8000": _serving(8000, OURS)}), preference=DECLARED)

    assert isinstance(plan, AttachToBackend)


# ── Planning: a conflict that must not be worked around ───────────────────────


def test_our_engagement_served_with_a_foreign_enterprise_tier_refuses() -> None:
    conflicted = EndpointObservation(
        port=8000,
        socket_taken=True,
        answers_probe=True,
        identity=BackendIdentity(
            repo_roots=(str(OURS.engagement_root), str(NEIGHBOUR.enterprise_root)),
            software_version="9.9.9",
        ),
    )

    plan = _plan(_world(**{"8000": conflicted}))

    assert isinstance(plan, RefuseEndpoint)
    assert "enterprise" in plan.reason


# ── Planning: a workspace that cannot state a claim ───────────────────────────


def test_without_a_claim_a_live_backend_is_the_best_evidence_there_is() -> None:
    plan = _plan(_world(**{"8000": _anonymous(8000)}), claim=None)

    assert isinstance(plan, AttachToBackend)
    assert plan.port == 8000


def test_without_a_claim_an_empty_machine_still_starts_on_the_preferred_port() -> None:
    assert _plan(_world(), claim=None) == StartBackendOn(port=8000)


def test_without_a_claim_no_derived_ports_are_considered() -> None:
    observe = _world(**{"8000": _silent_occupant(8000)})

    plan = _plan(observe, claim=None)

    assert isinstance(plan, RefuseEndpoint)
    assert observe.calls == [8000]  # type: ignore[attr-defined]


# ── Probing is the expensive part ─────────────────────────────────────────────


def test_every_port_is_observed_at_most_once() -> None:
    observe = _world(**{"8000": _serving(8000, NEIGHBOUR)})

    _plan(observe, recorded_port=8000)

    assert len(observe.calls) == len(set(observe.calls))  # type: ignore[attr-defined]
