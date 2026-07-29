"""Proposed resolutions for a quarantining profile conflict (WU-R2).

A merge conflict message names an attribute and the two incompatible types it was given.
This turns that into the three concrete moves an operator can make — rename the attribute so
the two definitions stop colliding, align their types, or unbind one contributing profile —
each filled in with the real attribute name, types, and bound-profile list rather than left
as generic advice.

Auto-migration is deliberately NOT offered here. The only unambiguous auto-migration the
plan sanctions is advancing an operator file that is byte-identical to an older SHIPPED
profile version (§5); no reusable profiles ship yet, so there is no shipped baseline to
compare against and every conflict is operator-authored — a human decision. This module
therefore only ever produces manual proposals, and ``is_auto_migratable`` is a hard False
that the reconciliation step relies on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# "Conflicting definitions for attribute 'X': type 'a' vs 'b'" — the one shape
# ``merge_property_schemas`` emits. Parsed rather than re-derived so the two never drift.
_CONFLICT_RE = re.compile(
    r"Conflicting definitions for attribute '(?P<attribute>[^']*)': type '(?P<left>[^']*)' vs '(?P<right>[^']*)'"
)


@dataclass(frozen=True)
class ProfileConflictResolution:
    """The proposed manual resolutions for one conflicting attribute on a (type,
    specialization) pair. ``proposals`` is ordered least-destructive first."""

    attribute: str
    left_type: str
    right_type: str
    proposals: tuple[str, ...]

    @property
    def is_auto_migratable(self) -> bool:
        # Every conflict here is operator-authored (no shipped baseline exists to advance
        # from), so none is ever migrated automatically. See the module docstring.
        return False


def propose_conflict_resolution(
    conflict_message: str, *, bound_profiles: tuple[str, ...] = ()
) -> ProfileConflictResolution | None:
    """Parse one ``merge_property_schemas`` conflict message into concrete proposals.

    Returns ``None`` when the message is not a type-conflict (the only conflict kind the
    merge emits today) — the caller keeps its own generic instruction rather than inventing
    a resolution for a shape this does not understand.
    """
    match = _CONFLICT_RE.search(conflict_message)
    if match is None:
        return None
    attribute = match.group("attribute")
    left, right = match.group("left"), match.group("right")
    proposals = [
        f"Rename one definition of '{attribute}' so the two no longer collide "
        "(the later-merged fragment is the one currently dropped).",
        f"Align the type of '{attribute}' — pick '{left}' or '{right}' in both definitions "
        "so the merge agrees.",
    ]
    if bound_profiles:
        named = ", ".join(repr(name) for name in bound_profiles)
        proposals.append(
            f"Unbind one contributing profile from this specialization (bound: {named}) so "
            f"only one definition of '{attribute}' remains."
        )
    else:
        proposals.append(
            f"Unbind the specialization's inline attribute or its attachment schema so only "
            f"one definition of '{attribute}' remains."
        )
    return ProfileConflictResolution(
        attribute=attribute, left_type=left, right_type=right, proposals=tuple(proposals)
    )


def resolution_instructions(resolution: ProfileConflictResolution | None, *, fallback: str) -> str:
    """Render proposals as one manual-instruction string, or ``fallback`` when the message
    was not a recognised type-conflict. Numbered so an operator can act on one and re-run."""
    if resolution is None:
        return fallback
    numbered = "; ".join(f"({i + 1}) {p}" for i, p in enumerate(resolution.proposals))
    return f"Resolve by one of: {numbered}"
