"""Gathering what the endpoint planner needs, and executing nothing.

The decision — attach here, start there, refuse and say why — is a pure function in
`domain.deployment.backend_endpoint`. This module is its impure half: it resolves which
repositories the workspace claims, looks at ports, and hands the planner an observer. Keeping the
two apart is what makes every multi-instance process state reachable in a test without a socket.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from pathlib import Path

from src.config.workspace_paths import resolve_workspace_repo_roots
from src.domain.deployment.backend_endpoint import (
    EndpointObservation,
    EndpointPlan,
    PortPreference,
    WorkspaceClaim,
    plan_endpoint,
)
from src.infrastructure.backend.backend_probe import (
    backend_port_preference,
    port_in_use,
    probe_backend,
    probe_identity_on_port,
)
from src.infrastructure.backend.backend_process import BackendInstance
from src.infrastructure.backend.backend_state import read_backend_state

logger = logging.getLogger(__name__)

ENV_ENGAGEMENT_ROOT = "ARCH_REPO_ROOT"
ENV_ENTERPRISE_ROOT = "ARCH_ENTERPRISE_ROOT"


def _env_root(name: str) -> Path | None:
    raw = os.getenv(name, "").strip()
    return Path(raw).expanduser().resolve() if raw else None


def claim_for_roots(engagement_root: Path | None, enterprise_root: Path | None) -> WorkspaceClaim | None:
    """The claim a backend serving these roots satisfies. None when there is no engagement root.

    Resolved here, once, because the identity endpoint publishes resolved roots and the comparison
    is string equality: a claim carrying an unresolved symlink would never match its own backend.
    """
    if engagement_root is None:
        return None
    return WorkspaceClaim(
        engagement_root=engagement_root.resolve(),
        enterprise_root=enterprise_root.resolve() if enterprise_root is not None else None,
    )


def workspace_claim(start: Path | None = None) -> WorkspaceClaim | None:
    """What the workspace at `start` expects its backend to serve.

    Environment overrides come first because they are what the backend process itself would serve;
    otherwise the arch-init state and `arch-workspace.yaml` answer, through the one resolver the
    rest of the system uses. None means the workspace cannot say — an uninitialised directory — and
    the planner then has nothing to compare, which it reports rather than guesses around.
    """
    engagement = _env_root(ENV_ENGAGEMENT_ROOT)
    enterprise = _env_root(ENV_ENTERPRISE_ROOT)
    if engagement is not None:
        return claim_for_roots(engagement, enterprise)

    roots = resolve_workspace_repo_roots(start or Path.cwd())
    if roots is None:
        logger.warning(
            "Workspace at %s declares no repository roots, so a backend on a shared port cannot be "
            "confirmed to serve this workspace. Run `arch-init` to remove the ambiguity.",
            start or Path.cwd(),
        )
        return None
    resolved_engagement, resolved_enterprise = roots
    return claim_for_roots(resolved_engagement, enterprise or resolved_enterprise)


#: How long a candidate port gets to accept a connection before it counts as free. Short because the
#: question is only "is anything listening on loopback", and a plan asks it of every candidate: at the
#: HTTP probe's timeout, walking nine free ports took twelve seconds and outlasted the deadline the
#: caller was waiting under.
FREE_PORT_TIMEOUT_SECONDS = 0.25


def observe_endpoint(port: int, *, timeout_s: float = 1.0) -> EndpointObservation:
    """One look at one port: is it held, does it answer, and what does it say it serves.

    Cheapest question first: an unheld port needs no HTTP at all, and most candidates are unheld.
    """
    if not port_in_use(port=port, timeout_s=FREE_PORT_TIMEOUT_SECONDS):
        return EndpointObservation(port=port, socket_taken=False, answers_probe=False)
    answers = probe_backend(port, timeout_s=timeout_s)
    return EndpointObservation(
        port=port,
        socket_taken=True,
        answers_probe=answers,
        identity=probe_identity_on_port(port, timeout_s=timeout_s) if answers else None,
    )


def plan_workspace_endpoint(
    *,
    cwd: Path | None = None,
    explicit_port: int | None = None,
    may_start: bool,
    claim: WorkspaceClaim | None = None,
    preference: PortPreference | None = None,
) -> EndpointPlan:
    """Which backend this workspace may use, or where it may start one.

    `claim` and `preference` are accepted so the backend process itself can plan from the roots it
    is about to serve — the roots its CLI arguments name, which no file has recorded yet.
    """
    workspace = cwd or Path.cwd()
    resolved_claim = claim if claim is not None else workspace_claim(workspace)
    resolved_preference = (
        preference
        if preference is not None
        else backend_port_preference(start=workspace, explicit_port=explicit_port)
    )
    state = read_backend_state(workspace)
    plan = plan_endpoint(
        claim=resolved_claim,
        preference=resolved_preference,
        recorded_port=state["port"] if state is not None else None,
        may_start=may_start,
        observe=observe_endpoint,
    )
    logger.info(
        "Endpoint plan for %s (claim=%s, preferred=%s from %s, recorded=%s): %s",
        workspace,
        resolved_claim.engagement_root if resolved_claim is not None else None,
        resolved_preference.port,
        resolved_preference.authority,
        state["port"] if state is not None else None,
        plan,
    )
    return plan


def foreign_occupant(port: int, claim: WorkspaceClaim | None, *, pid: int | None = None) -> dict[str, object] | None:
    """A report of a backend on `port` serving some *other* workspace, or None.

    None when the occupant cannot be attributed at all — nothing answers, it reports no roots, or this
    workspace states no claim — because those cases keep their own, less certain verdicts. Only a
    positive statement that it serves other repositories disqualifies a backend here, and that
    statement is what keeps a status report and a stop request inside the workspace that made them.
    """
    if claim is None:
        return None
    identity = probe_identity_on_port(port)
    if identity is None or identity.serves(claim.engagement_root):
        return None
    logger.warning(
        "Port %s is serving another workspace (%s); this workspace expects %s",
        port,
        ", ".join(identity.repo_roots),
        claim.engagement_root,
    )
    return {
        "running": False,
        "reason": "foreign_workspace",
        "port": port,
        "served_roots": list(identity.repo_roots),
        **({"pid": pid} if pid is not None else {}),
    }


def instances_serving_workspace(
    instances: Sequence[BackendInstance], claim: WorkspaceClaim | None
) -> list[BackendInstance]:
    """The backend processes that answer for *this* workspace, whatever port they ended up on.

    A record can be lost — deleted, never written, or removed by something else — and a backend whose
    port moved is then invisible to a search by port. Asking each listening socket what it serves finds
    it, and finds only it: the same question that keeps a stop request off a neighbour's process.
    """
    if claim is None:
        return []
    return [
        instance
        for instance in instances
        if any(port_serves_workspace(port, claim) for port in instance["ports"])
    ]


def port_serves_workspace(port: int, claim: WorkspaceClaim | None, *, timeout_s: float = 1.0) -> bool:
    """Whether the backend listening on `port` serves this workspace.

    False when it serves something else, when it will not say, and when the workspace cannot state a
    claim: a process nobody can attribute to this workspace must never be reported as its own, and
    must never be signalled — that is how one workspace's `--stop` reached another's backend.
    """
    if claim is None:
        return False
    identity = probe_identity_on_port(port, timeout_s=timeout_s)
    return identity is not None and identity.serves(claim.engagement_root)
