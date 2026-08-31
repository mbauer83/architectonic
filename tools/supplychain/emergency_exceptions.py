#!/usr/bin/env python
"""The one way to take a pin younger than the floor, and the reason it cannot become permanent.

**Why this exists.** The age floor and the vulnerability gate can give opposite instructions: when
the only fix for a known vulnerability was published an hour ago, one control says take it and the
other says wait. Without a sanctioned way through, the likely outcome is that someone disables a
control — and a disabled control is not visible in a diff the way a named exception is.

**Why it expires.** An exception with no expiry is a permanent hole that reads as a decision. Each
entry names one package at one version, says why, and states the day it stops applying. Past that day
it admits nothing, and it fails the gate in its own right until it is removed: a register that
accumulates spent entries is one nobody reads.

**What it does not cover.** Version control and direct-archive pins. Those are refused outright, not
by paperwork — over a permanent git dependency an expiring exception becomes a build that breaks on a
schedule, which is the wrong instrument. If a real need appears, it wants a second, non-expiring one.

The licence gate's `ACKNOWLEDGED` map is the sanctioned shape this follows, made typed and dated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

#: The longest an emergency may last. A month is generous for "the fix is hours old"; anything the
#: project needs for longer is a decision about a dependency, and belongs in a commit that says so.
MAX_LIFETIME = timedelta(days=30)

#: The shortest a justification can be and still say anything. Not a style rule: an entry that says
#: "temporary" is the same permanent hole this module exists to prevent.
_MIN_JUSTIFICATION = 40


@dataclass(frozen=True, slots=True)
class EmergencyException:
    """One package, at one version, admitted under the floor until a stated day.

    Refuses to exist malformed. An entry that cannot be constructed cannot be committed, which is
    cheaper than a gate that reports it later.
    """

    package: str
    version: str
    declared: date
    expires: date
    justification: str

    def __post_init__(self) -> None:
        if not self.package or not self.version:
            raise ValueError("an emergency exception names one package at one version")
        if self.expires <= self.declared:
            raise ValueError(f"{self}: expires on or before the day it was declared")
        if self.expires - self.declared > MAX_LIFETIME:
            raise ValueError(
                f"{self}: lasts {(self.expires - self.declared).days} days, over the "
                f"{MAX_LIFETIME.days}-day maximum. A longer need is a decision about a dependency."
            )
        if len(self.justification.strip()) < _MIN_JUSTIFICATION:
            raise ValueError(f"{self}: justification is too short to say why the floor was waived")

    def __str__(self) -> str:
        return f"{self.package} {self.version} (expires {self.expires.isoformat()})"

    def admits(self, package: str, version: str, *, on: date) -> bool:
        return (package, version) == (self.package, self.version) and on < self.expires


#: Every emergency exception in force. Empty is the expected state: an entry here means a control was
#: overridden, and it should be short-lived enough that its removal is part of the same week's work.
REGISTER: tuple[EmergencyException, ...] = ()


def admitting(
    register: tuple[EmergencyException, ...], package: str, version: str, *, on: date
) -> EmergencyException | None:
    return next((entry for entry in register if entry.admits(package, version, on=on)), None)


def expired(register: tuple[EmergencyException, ...], *, on: date) -> tuple[EmergencyException, ...]:
    """Spent entries. They admit nothing, and the gate refuses until they are taken out."""
    return tuple(entry for entry in register if on >= entry.expires)
