"""Which backend a workspace may talk to, and where it may start one of its own (pure).

A backend serves exactly one engagement repository, but every workspace on a machine ships the
same default port. A socket answering there therefore proves only that *something* answers, and
choosing an endpoint by port alone is how an agent working one checkout was served another
checkout's model for a whole session: the stdio bridge found 8000 occupied, called that "already
running", and proxied every tool call into a foreign workspace — silently, because both answers
are well-formed.

The rule stated here: a workspace attaches only to a backend that *says* it serves that
workspace's engagement repository (`GET /api/backend-identity`), and otherwise starts its own on
a port nothing else holds. A port is where to look first; it is never the proof.

Observations are supplied by the caller and the plan is a value the caller executes, so every
process state a machine can be in — nothing running, our backend up, a foreign backend on the
preferred port, a stale record, an exhausted range — is reachable in a test without a socket.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.domain.deployment.endpoint_vocabulary import (
    BackendIdentity,
    EndpointObservation,
    EndpointState,
    PortAuthority,
    PortPreference,
    WorkspaceClaim,
)

# Re-exported: these are the vocabulary of an endpoint decision and every caller of the planner
# speaks it, so moving them out of this module is not a reason to move every import.
__all__ = [
    "BackendIdentity",
    "EndpointObservation",
    "EndpointState",
    "PortAuthority",
    "PortPreference",
    "WorkspaceClaim",
]

from src.domain.deployment._endpoint_refusals import (
    declared_port_taken_reason,
    enterprise_conflict_reason,
    no_free_port_reason,
    nothing_serving_reason,
)

#: Where a workspace looks when its preferred port is held by something else. Above the shipped
#: default and below the ephemeral range, so a derived port collides neither with the instance
#: that took the default nor with a kernel-assigned client port.
DERIVED_PORT_FLOOR = 8100
DERIVED_PORT_CEILING = 8499

#: How many consecutive ports from the derived one a workspace considers before reporting that it
#: has nowhere to start. Bounded so an exhausted range refuses with a reason instead of scanning.
DERIVED_PORT_ATTEMPTS = 8


def classify_endpoint(observation: EndpointObservation, claim: WorkspaceClaim | None) -> EndpointState:
    """Judge one observation against the workspace's claim.

    A workspace with no resolvable claim cannot tell its own backend from another's, so nothing is
    ever `ours` for it — the caller degrades to liveness, loudly, rather than guessing.
    """
    if not observation.socket_taken and not observation.answers_probe:
        return "free"
    identity = observation.identity
    if identity is None:
        return "unidentified" if observation.answers_probe else "occupied"
    if claim is None or not identity.repo_roots:
        # A backend that reports no roots serves nothing yet, so it is evidence of neither ownership
        # nor foreignness — and a workspace with no claim cannot tell one from the other at all.
        return "unidentified"
    if not identity.serves(claim.engagement_root):
        return "foreign"
    if claim.enterprise_root is not None and not identity.serves(claim.enterprise_root):
        return "enterprise_conflict"
    return "ours"





@dataclass(frozen=True)
class AttachToBackend:
    """A backend serving this workspace is already up at `port`."""

    port: int
    identity: BackendIdentity | None = None


@dataclass(frozen=True)
class StartBackendOn:
    """Nothing serves this workspace yet; `port` is free for it.

    `moved_from` records the preferred port a foreign occupant made unusable, so the caller can say
    why the address changed instead of leaving the operator to discover it.
    """

    port: int
    moved_from: int | None = None
    moved_because: EndpointState | None = None


@dataclass(frozen=True)
class RefuseEndpoint:
    """No endpoint may be used, and `reason` says what the operator can do about it."""

    reason: str


EndpointPlan = AttachToBackend | StartBackendOn | RefuseEndpoint

Observer = Callable[[int], EndpointObservation]


def derived_port(fingerprint: str) -> int:
    """This workspace's own port: deterministic, so a restart returns to the same address."""
    span = DERIVED_PORT_CEILING - DERIVED_PORT_FLOOR + 1
    return DERIVED_PORT_FLOOR + int(fingerprint[:8], 16) % span


def derived_port_sequence(fingerprint: str, *, attempts: int = DERIVED_PORT_ATTEMPTS) -> tuple[int, ...]:
    """The derived port and its successors, wrapped inside the derived range."""
    span = DERIVED_PORT_CEILING - DERIVED_PORT_FLOOR + 1
    first = derived_port(fingerprint) - DERIVED_PORT_FLOOR
    return tuple(DERIVED_PORT_FLOOR + (first + offset) % span for offset in range(attempts))


def endpoint_candidates(
    *,
    preference: PortPreference,
    claim: WorkspaceClaim | None,
    recorded_port: int | None,
) -> tuple[int, ...]:
    """Every port worth looking at, nearest evidence first.

    The recorded port leads because a running backend wrote it, so it is the only candidate that
    reflects what this workspace actually did last; the preferred port follows as the address
    everything else (the GUI, the docs, a browser tab) expects.

    Derived ports appear only behind a *default* preference. A stated port is never moved off, so
    looking for somewhere else to go would be asking a question whose answer cannot be used — and
    every candidate costs a connection attempt against a machine that may not refuse promptly.
    """
    derived = (
        derived_port_sequence(claim.fingerprint) if claim is not None and not preference.is_declared else ()
    )
    ordered = [*([recorded_port] if recorded_port is not None else []), preference.port, *derived]
    return tuple(dict.fromkeys(ordered))


def plan_endpoint(
    *,
    claim: WorkspaceClaim | None,
    preference: PortPreference,
    recorded_port: int | None,
    may_start: bool,
    observe: Observer,
) -> EndpointPlan:
    """Decide which backend to use, or where to start one, or why neither is possible.

    Every port is observed at most once: the search for an existing backend and the search for a
    free port walk the same candidates, and probing is the expensive part.
    """
    observations: dict[int, EndpointObservation] = {}

    def state_of(port: int) -> tuple[EndpointState, EndpointObservation]:
        observation = observations.get(port)
        if observation is None:
            observation = observe(port)
            observations[port] = observation
        return classify_endpoint(observation, claim), observation

    candidates = endpoint_candidates(preference=preference, claim=claim, recorded_port=recorded_port)

    existing = _existing_backend(candidates, state_of, claim=claim)
    if existing is not None:
        return existing
    if not may_start:
        return RefuseEndpoint(reason=nothing_serving_reason(candidates, state_of, claim=claim))
    return _somewhere_to_start(candidates, state_of, preference=preference)


def _existing_backend(
    candidates: tuple[int, ...],
    state_of: Callable[[int], tuple[EndpointState, EndpointObservation]],
    *,
    claim: WorkspaceClaim | None,
) -> EndpointPlan | None:
    """An attachable backend, a conflict that must be reported, or None to keep looking."""
    for port in candidates:
        state, observation = state_of(port)
        if state == "ours":
            return AttachToBackend(port=port, identity=observation.identity)
        if state == "enterprise_conflict":
            return RefuseEndpoint(reason=enterprise_conflict_reason(port, observation, claim))
    if claim is None:
        return _liveness_only_attachment(candidates, state_of)
    return None


def _liveness_only_attachment(
    candidates: tuple[int, ...],
    state_of: Callable[[int], tuple[EndpointState, EndpointObservation]],
) -> EndpointPlan | None:
    """Without a claim, an answering backend is the best evidence there is."""
    for port in candidates:
        state, observation = state_of(port)
        if state == "unidentified":
            return AttachToBackend(port=port, identity=observation.identity)
    return None


def _somewhere_to_start(
    candidates: tuple[int, ...],
    state_of: Callable[[int], tuple[EndpointState, EndpointObservation]],
    *,
    preference: PortPreference,
) -> EndpointPlan:
    preferred_state, preferred_observation = state_of(preference.port)
    if preferred_state == "free":
        return StartBackendOn(port=preference.port)
    if preference.is_declared:
        return RefuseEndpoint(
            reason=declared_port_taken_reason(preference, preferred_state, preferred_observation)
        )
    for port in candidates:
        if port == preference.port:
            continue
        state, _ = state_of(port)
        if state == "free":
            return StartBackendOn(port=port, moved_from=preference.port, moved_because=preferred_state)
    return RefuseEndpoint(reason=no_free_port_reason(candidates, preference))
