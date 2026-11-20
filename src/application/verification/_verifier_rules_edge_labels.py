"""Verifier rule: an edge-label override that names no relation the diagram draws (E410)."""

from __future__ import annotations

import re

from src.application.modeling.diagram_identities import alias_by_instance, drawn_relation_ends
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.domain.diagrams.relation_key import MalformedRelationKey, read_relation_key

_ARROW_LINE = re.compile(r"^\s*([\w-]+)\s+[-.*|o<>][^\n:]*?[-.*|o<>]\s+([\w-]+)", re.MULTILINE)


def _pairs_drawn(body: str) -> set[frozenset[str]]:
    """The alias pairs a body joins with a visible arrow, either way round."""
    pairs: set[frozenset[str]] = set()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("'") or "[hidden]" in stripped:
            continue
        match = _ARROW_LINE.match(line)
        if match:
            pairs.add(frozenset((match.group(1).replace("-", "_"), match.group(2).replace("-", "_"))))
    return pairs


def check_edge_label_overrides(content: str, fm: dict, result: VerificationResult, loc: str) -> None:
    """Flag every ``edge-labels`` key that is not the key of a relation this diagram draws.

    A label is keyed by its drawn relation — the connection, and the instances at its ends where
    either is a further occurrence — so the question is asked of what the diagram records. A key in
    the retired alias-pair form is refused with what to run.

    **A hand-written body is asked as well.** On a ``manual-layout`` diagram the body is the only
    statement of what is drawn, and its recorded connections are a claim about it that can be wrong.
    There a label must also sit on a relation whose two ends the body joins with an arrow; an end
    whose alias the diagram's own statements cannot tell is not judged.
    """
    raw = fm.get("edge-labels")
    if not isinstance(raw, dict) or not raw:
        return
    drawn = drawn_relation_ends(
        fm.get("connection-ids-used"), fm.get("diagram-entities"), fm.get("connections"), fm.get("bindings")
    )
    hand_written = fm.get("manual-layout") is True
    aliases = alias_by_instance(fm) if hand_written else {}
    pairs = _pairs_drawn(content) if hand_written else set()
    for key in raw:
        try:
            named = read_relation_key(str(key)).text
        except MalformedRelationKey as refusal:
            result.issues.append(Issue(Severity.ERROR, "E410", f"edge-labels: {refusal}", loc))
            continue
        ends = drawn.get(named)
        if ends is None:
            result.issues.append(Issue(
                Severity.ERROR,
                "E410",
                f"edge-labels key '{key}' names no relation this diagram draws (dangling override)",
                loc,
            ))
            continue
        source, target = aliases.get(ends[0]), aliases.get(ends[1])
        if hand_written and source and target and frozenset((source, target)) not in pairs:
            result.issues.append(Issue(
                Severity.ERROR,
                "E410",
                f"edge-labels key '{key}' names a relation this diagram records but its hand-written body "
                f"draws no arrow between {source} and {target} (dangling override)",
                loc,
            ))
