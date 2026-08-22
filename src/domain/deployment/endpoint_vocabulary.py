"""The vocabulary of an endpoint decision: what a workspace claims, and what was found at a port.

Its own module because two modules speak it and neither should depend on the other. The planner
decides, `_endpoint_refusals` words the refusals, and the planner imports the wording — so the
wording naming the planner's own types made a cycle. It was a `TYPE_CHECKING` cycle and therefore
invisible at runtime, but a type checker resolving it has to pick an order, and whichever it picked
decided whether the names resolved: `uv run zuban check` reported `Invalid type comment or
annotation` on about four runs in ten, and on every run over that file alone.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class BackendIdentity:
    """What a backend answers about itself: the roots it serves, and the software serving them.

    `repo_roots` are realpath-normalized by the endpoint that publishes them, so a claim compared
    against them must be normalized the same way — string equality is the whole comparison.
    """

    repo_roots: tuple[str, ...]
    software_version: str

    def serves(self, root: Path) -> bool:
        return str(root) in self.repo_roots


@dataclass(frozen=True)
class WorkspaceClaim:
    """The repositories a workspace expects its own backend to serve.

    Both roots are already resolved by whoever built the claim; this type does no filesystem work.
    """

    engagement_root: Path
    enterprise_root: Path | None = None

    @property
    def fingerprint(self) -> str:
        """A stable digest of the roots — what makes a workspace's derived port its own.

        Derived from the roots rather than the workspace directory: two directories configured to
        serve the same repositories are one instance, and sharing a backend between them is right.
        """
        material = f"{self.engagement_root}\n{self.enterprise_root or ''}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


#: What was found at a port, judged against what the workspace expects there.
#:
#: * `free` — nothing holds the port, so a backend may start on it
#: * `ours` — a backend that serves this workspace's engagement repository
#: * `foreign` — a backend serving some other workspace
#: * `enterprise_conflict` — our engagement repository, served with a different enterprise tier
#: * `unidentified` — something answers but will not say what it serves (a pre-identity backend,
#:   or an unrelated HTTP service)
#: * `occupied` — the port is bound by something that does not answer the probe at all
EndpointState = Literal["free", "ours", "foreign", "enterprise_conflict", "unidentified", "occupied"]


@dataclass(frozen=True)
class EndpointObservation:
    """One look at one port."""

    port: int
    socket_taken: bool
    answers_probe: bool
    identity: BackendIdentity | None = None


#: Where a preferred port came from. `command` (a CLI flag) and `environment` name this run, and
#: `workspace_config` names this workspace — all three are statements, and a statement is obeyed or
#: refused, never quietly moved. `settings_document` is the shipped default every clone carries, so
#: it is a preference a workspace may yield when something else already holds it.
PortAuthority = Literal["command", "environment", "workspace_config", "settings_document"]


@dataclass(frozen=True)
class PortPreference:
    port: int
    authority: PortAuthority

    @property
    def is_declared(self) -> bool:
        """Whether this port was stated for this workspace, as opposed to inherited as a default."""
        return self.authority != "settings_document"
