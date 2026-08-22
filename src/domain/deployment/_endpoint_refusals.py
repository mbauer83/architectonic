"""Why a workspace may not use an endpoint, in words an operator can act on (pure).

Separate from the planner because a refusal is only useful if it says what to do next, and that
wording is worth reading on its own: "the port is in use" leaves an operator to guess, while naming
the repositories the occupant serves and the file that stated the port does not.

The types come from `endpoint_vocabulary`, not from the planner. Reaching back into the planner for
them made a `TYPE_CHECKING` cycle that a type checker had to break by guessing an order.
"""

from __future__ import annotations

from collections.abc import Callable

from src.domain.deployment.endpoint_vocabulary import (
    EndpointObservation,
    EndpointState,
    PortPreference,
    WorkspaceClaim,
)

#: How the planner offers a port's judgement to a message that has to describe it.
StateOf = Callable[[int], tuple[EndpointState, EndpointObservation]]

#: Which knob set a port, for a message that tells the operator where to change it.
PORT_AUTHORITY_SOURCES = {
    "command": "--port",
    "environment": "ARCH_BACKEND_PORT",
    "workspace_config": "arch-workspace.yaml (backend.port)",
    "settings_document": "config/settings.yaml (backend.port)",
}


def served_roots(observation: EndpointObservation) -> str:
    identity = observation.identity
    if identity is None or not identity.repo_roots:
        return "an unknown repository"
    return ", ".join(identity.repo_roots)


def occupant(port: int, state: EndpointState, observation: EndpointObservation) -> str:
    match state:
        case "foreign":
            return f"port {port} is serving another workspace ({served_roots(observation)})"
        case "unidentified":
            return f"port {port} answers but does not report which repositories it serves"
        case "occupied":
            return f"port {port} is held by a process that is not an architecture backend"
        case _:
            return f"port {port} is unavailable"


def enterprise_conflict_reason(
    port: int, observation: EndpointObservation, claim: WorkspaceClaim | None
) -> str:
    expected = claim.enterprise_root if claim is not None else None
    return (
        f"The backend on port {port} serves this workspace's engagement repository but a different "
        f"enterprise tier ({served_roots(observation)}; this workspace expects {expected}). Stop it "
        "with `arch-backend --stop`, or reconcile arch-workspace.yaml, before continuing."
    )


def nothing_serving_reason(
    candidates: tuple[int, ...], state_of: StateOf, *, claim: WorkspaceClaim | None
) -> str:
    served = claim.engagement_root if claim is not None else "this workspace"
    findings: list[str] = []
    for port in candidates:
        state, observation = state_of(port)
        if state != "free":
            findings.append(occupant(port, state, observation))
    detail = f" ({'; '.join(findings)})" if findings else ""
    return f"The backend for {served} is not running{detail}. Start it with `arch-backend --daemon`."


def declared_port_taken_reason(
    preference: PortPreference, state: EndpointState, observation: EndpointObservation
) -> str:
    return (
        f"{occupant(preference.port, state, observation)}, and port {preference.port} was named by "
        f"{PORT_AUTHORITY_SOURCES[preference.authority]} — a stated port is not moved silently. Free "
        "the port, stop the other backend, or name a different one."
    )


def no_free_port_reason(candidates: tuple[int, ...], preference: PortPreference) -> str:
    return (
        f"No free port for this workspace's backend: {preference.port} and every derived candidate "
        f"({', '.join(str(port) for port in candidates)}) are in use. Stop a backend you no longer "
        "need, or name a free port with `arch-backend --port`."
    )
