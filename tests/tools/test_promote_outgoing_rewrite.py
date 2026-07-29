"""Outgoing-file rewriting during promotion: a dropped connection is dropped WHOLE
(heading, description, trailing blanks), and a heading directly following a dropped
section is still resolved or dropped on its own merits — neither its description may
leak as floating prose, nor may an unresolvable heading be copied verbatim."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.infrastructure.write.artifact_write._promote_file_ops import rewrite_outgoing


@dataclass
class _Plan:
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Result:
    plan: _Plan = field(default_factory=_Plan)


_CONTENT = """\
---
source-entity: REQ@1.Src.source
version: 0.1.0
status: draft
---

<!-- §connections -->

### archimate-realization → PRI@1.Kept.kept-principle

Kept description.

### archimate-realization → PRI@1.Drop.engagement-only-principle

Leaky description that must vanish with its dropped section.

### archimate-composition → REQ@1.Gar.proxied-target

Resolved description.
"""


def _resolver(target_id: str) -> str | None:
    return {
        "PRI@1.Kept.kept-principle": "PRI@1.Kept.kept-principle",
        "REQ@1.Gar.proxied-target": "REQ@1.Real.enterprise-target",
    }.get(target_id)


def test_dropped_section_vanishes_whole_and_next_heading_still_resolves() -> None:
    result = _Result()
    rewritten = rewrite_outgoing(_CONTENT, resolve_target=_resolver, result=result)

    assert "Kept description." in rewritten
    assert "engagement-only-principle" not in rewritten
    assert "Leaky description" not in rewritten, "dropped sections must not leak their prose"
    assert "### archimate-composition → REQ@1.Real.enterprise-target" in rewritten, (
        "a heading after a dropped section must still be target-resolved"
    )
    assert "REQ@1.Gar.proxied-target" not in rewritten
    assert len(result.plan.warnings) == 1


def test_consecutive_dropped_sections_each_decide_for_themselves() -> None:
    content = _CONTENT.replace(
        "### archimate-composition → REQ@1.Gar.proxied-target",
        "### archimate-composition → REQ@1.Gone.also-engagement-only",
    ).replace("Resolved description.", "Second leaky description.")
    result = _Result()
    rewritten = rewrite_outgoing(content, resolve_target=_resolver, result=result)

    assert "also-engagement-only" not in rewritten
    assert "Second leaky description" not in rewritten
    assert "Kept description." in rewritten
    assert len(result.plan.warnings) == 2
