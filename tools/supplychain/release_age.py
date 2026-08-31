#!/usr/bin/env python
"""The release-age floor: no pin younger than 24 hours may enter a committed lockfile.

**Why a gate over the lock rather than a constraint on the resolver.** "No pin younger than 24h" is
monotone over a committed lockfile — once a lock passes it passes forever, because pins only get
older. So a gate is deterministic and stable, while a resolution setting is neither: uv accepts a
rolling ``exclude-newer`` in ``[tool.uv]`` and resolves it to a moving timestamp, which makes every
``uv sync`` re-resolve and rewrite the committed lock. Resolution settings stay ergonomics (they stop
a developer picking a fresh version by accident); the gate is the enforcement.

**Why the youngest artifact and not the package.** A lock records an upload time per *artifact* — an
sdist plus a wheel per platform — and a package can carry a year-old sdist beside a wheel published
an hour ago. The lock is multi-platform, any of those wheels may be what a supported target
installs, so the rule takes the **youngest** artifact. Aggregating on the oldest, or on whichever
wheel this machine happens to select, admits exactly the case the floor exists to catch.

**Why non-registry sources are refused rather than exempted.** An immutable commit sha proves content
*identity*, not that the content survived the floor, so integrity alone is not a pass. The project's
own editable entry is different in kind: it is inside the workspace, it is not conveyed from a
registry, and a rule that failed it would make the project need a permanent exception to itself —
the allowlist-that-must-stay-empty shape this repository refuses. So a workspace path passes by
construction, and everything else third-party fails until it carries age evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from tools.supplychain.emergency_exceptions import EmergencyException, admitting

#: How old every locked artifact must be. A day is long enough for a compromised or withdrawn
#: release to be noticed and yanked, and short enough that a security fix is not held for a week.
FLOOR = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class RegistryArtifacts:
    """A pin resolved from a package registry, with one upload time per locked artifact.

    ``None`` stands for an artifact the lock names without an upload time — evidence that is absent,
    which the policy treats as evidence that is missing rather than as a pass.
    """

    uploaded: tuple[datetime | None, ...]


@dataclass(frozen=True, slots=True)
class LocalPath:
    """A pin resolved from the filesystem: the editable project, a workspace member, a stray path."""

    path: Path


@dataclass(frozen=True, slots=True)
class VcsRef:
    """A pin resolved from version control. ``immutable`` means a full commit sha rather than a ref."""

    reference: str
    immutable: bool


@dataclass(frozen=True, slots=True)
class ArchiveUrl:
    """A pin resolved from a direct archive URL. ``hashed`` means the lock records its digest."""

    url: str
    hashed: bool


#: The length of a full git commit sha. A revision shorter than this is a name, and a name can be
#: repointed at other content under an unchanged lock entry.
_SHA_LENGTH = 40


def vcs_ref(reference: str) -> VcsRef:
    """Classify a version-control pin. Both lockfiles spell the resolved revision as a `#`-fragment.

    Immutability is decided here rather than in either reader, because what makes a ref immutable is
    the same question as what the verdict below turns on.
    """
    _, _, revision = reference.rpartition("#")
    return VcsRef(
        reference=reference,
        immutable=len(revision) == _SHA_LENGTH and all(c in "0123456789abcdef" for c in revision),
    )


#: Every shape a lock entry's origin can take. Closed, because a new shape is a decision about what
#: the project is willing to depend on — not a case for a reader to invent a default for.
Source = RegistryArtifacts | LocalPath | VcsRef | ArchiveUrl


@dataclass(frozen=True, slots=True)
class Admitted:
    reason: str


@dataclass(frozen=True, slots=True)
class Refused:
    reason: str


Verdict = Admitted | Refused


@dataclass(frozen=True, slots=True)
class LockedPackage:
    """One entry of a committed lockfile, reduced to what the age policy needs to judge it."""

    name: str
    version: str
    source: Source

    def __str__(self) -> str:
        return f"{self.name} {self.version}"


def judge(
    package: LockedPackage,
    *,
    now: datetime,
    workspace: Path,
    register: tuple[EmergencyException, ...] = (),
    floor: timedelta = FLOOR,
) -> Verdict:
    """The verdict a lock entry earns, including the one way past the floor.

    An emergency exception waives the **age** of a registry artifact and nothing else. A
    version-control or direct-archive pin stays refused: over a permanent git dependency an expiring
    exception becomes a build that breaks on a schedule, which is the wrong instrument for it.
    """
    verdict = assess(package.source, now=now, workspace=workspace, floor=floor)
    if isinstance(verdict, Admitted) or not isinstance(package.source, RegistryArtifacts):
        return verdict
    waiver = admitting(register, package.name, package.version, on=now.date())
    if waiver is None:
        return verdict
    return Admitted(f"{verdict.reason}; admitted by an emergency exception — {waiver.justification}")


def assess(source: Source, *, now: datetime, workspace: Path, floor: timedelta = FLOOR) -> Verdict:
    """Judge one lock entry's origin against the floor. Pure: every input is an argument."""
    match source:
        case RegistryArtifacts(uploaded=uploaded):
            return _assess_registry(uploaded, now=now, floor=floor)
        case LocalPath(path=path):
            return (
                Admitted(f"first-party workspace source at {path}")
                if _inside(path, workspace)
                else Refused(f"local path outside the workspace: {path}")
            )
        case VcsRef(reference=reference, immutable=immutable):
            return Refused(
                f"version-control pin {reference} carries no age evidence"
                if immutable
                else f"mutable version-control ref {reference}: its content can change under this lock"
            )
        case ArchiveUrl(url=url, hashed=hashed):
            return Refused(
                f"direct archive {url} carries no age evidence"
                if hashed
                else f"direct archive {url} is neither hashed nor dated"
            )


def _assess_registry(
    uploaded: Iterable[datetime | None], *, now: datetime, floor: timedelta
) -> Verdict:
    times = tuple(uploaded)
    if not times:
        return Refused("the lock records no artifact for this pin")
    if any(time is None for time in times):
        return Refused(f"{sum(time is None for time in times)} of {len(times)} artifacts have no upload time")
    dated = tuple(time for time in times if time is not None)
    youngest = max(dated)
    if youngest > now:
        return Refused(f"youngest artifact is dated {youngest.isoformat()}, in the future")
    age = now - youngest
    if age < floor:
        return Refused(f"youngest of {len(dated)} artifacts is {_spoken(age)} old, under the {_spoken(floor)} floor")
    return Admitted(f"youngest of {len(dated)} artifacts is {_spoken(age)} old")


def _inside(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
    except ValueError:
        return False
    return True


def _spoken(span: timedelta) -> str:
    hours = span.total_seconds() / 3600
    return f"{hours:.1f}h" if hours < 48 else f"{hours / 24:.1f}d"
