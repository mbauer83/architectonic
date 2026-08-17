"""Proposed resolutions for a quarantining profile conflict (WU-R2).

A merge conflict message names an attribute, the facet two definitions disagree about, and the
two values it was given. This turns that into the three concrete moves an operator can make —
rename the attribute so the two definitions stop colliding, align the facet, or unbind one
contributing profile — each filled in with the real attribute name, values, and bound-profile
list rather than left as generic advice.

Two facets decide: ``type`` and ``format``. They share one message shape and are parsed by one
expression, so a second deciding facet did not bring a second reader with it.

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

from src.domain.ontology_representation.profiles import DECIDING_FACETS

# "Conflicting definitions for attribute 'X': <facet> 'a' vs 'b'" — the one shape
# ``merge_property_schemas`` emits, for either deciding facet. Parsed rather than re-derived so
# the two never drift; the facet alternation is spelled from the emitter's own tuple.
_CONFLICT_RE = re.compile(
    r"Conflicting definitions for attribute '(?P<attribute>[^']*)': "
    r"(?P<facet>" + "|".join(DECIDING_FACETS) + r") '(?P<left>[^']*)' vs '(?P<right>[^']*)'"
)


@dataclass(frozen=True)
class ProfileConflictResolution:
    """The proposed manual resolutions for one conflicting attribute on a (type,
    specialization) pair. ``proposals`` is ordered least-destructive first."""

    attribute: str
    #: Which facet the two definitions disagree about — ``type`` or ``format``.
    facet: str
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

    Returns ``None`` when the message names no deciding facet — the caller keeps its own generic
    instruction rather than inventing a resolution for a shape this does not understand.
    """
    match = _CONFLICT_RE.search(conflict_message)
    if match is None:
        return None
    attribute = match.group("attribute")
    facet = match.group("facet")
    left, right = match.group("left"), match.group("right")
    proposals = [
        f"Rename one definition of '{attribute}' so the two no longer collide "
        "(the later-merged fragment is the one currently dropped).",
        f"Align the {facet} of '{attribute}' — pick '{left}' or '{right}' in both definitions "
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
        attribute=attribute, facet=facet, left_type=left, right_type=right,
        proposals=tuple(proposals),
    )


def resolution_instructions(resolution: ProfileConflictResolution | None, *, fallback: str) -> str:
    """Render proposals as one manual-instruction string, or ``fallback`` when the message
    was not a recognised type-conflict. Numbered so an operator can act on one and re-run."""
    if resolution is None:
        return fallback
    numbered = "; ".join(f"({i + 1}) {p}" for i, p in enumerate(resolution.proposals))
    return f"Resolve by one of: {numbered}"
