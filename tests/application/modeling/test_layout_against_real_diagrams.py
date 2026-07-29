"""Auto-layout, run against every diagram the repository actually holds.

The unit tests next door prove the ordering rule on constructed bodies. They cannot show what
the rule does to real content, and that is precisely where a layout change does its damage:
it does not fail, it just quietly produces a worse picture in a diagram nobody reopens for a
month. This module is the counterweight — the same optimizer, over the real corpus, asserting
what must hold everywhere.

Both directions are covered, because a layout change is as likely to break something it should
not have touched as it is to fix what it aimed at:

* **Positive** — no grouping may end up with a sequencing edge pointing backwards along the
  spread axis, which is the defect being fixed.
* **Negative** — nothing but the order of hidden links may move. Element declarations, the
  direction directive, the connection lines, the number of constraints and the membership of
  every grouping all have to come out exactly as they went in.

Per the repository's testing rule these assert invariants rather than counts: authoring a new
diagram must never fail this file, only a regression in the optimizer may.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest import mock

import pytest

from src.application.modeling import artifact_write_layout as layout
from src.application.modeling.artifact_write_layout import (
    _directed_pairs,
    _parse_groupings,
    ensure_puml_layout,
    rebuild_puml_layout,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DIAGRAM_ROOT = REPO_ROOT / "engagements" / "ENG-ARCH-REPO" / "architecture-repository" / "diagram-catalog" / "diagrams"

HIDDEN_RE = re.compile(r"^\s*(\w+) -\[hidden\]\w+- (\w+)\s*$")


def _bodies() -> list[tuple[str, str]]:
    """Every stored PUML body, keyed by file name, with its frontmatter stripped."""
    if not DIAGRAM_ROOT.exists():
        return []
    found: list[tuple[str, str]] = []
    for path in sorted(DIAGRAM_ROOT.rglob("*.puml")):
        text = path.read_text(encoding="utf-8")
        marker = text.find("@startuml")
        if marker >= 0:
            found.append((path.name, text[marker:]))
    return found


BODIES = _bodies()


AUTO_MARKER = "' --- Auto-layout: spread elements within groupings ---"

#: Bodies the generator produced, i.e. the ones this optimizer is responsible for. A
#: hand-authored diagram may carry its own `-[hidden]` links for reasons of its own; those are
#: an author's decision, not this module's output, and must never be re-derived.
GENERATED = [(name, body) for name, body in BODIES if AUTO_MARKER in body]


def _without_auto_block(body: str) -> str:
    """The body as it looked before the optimizer ran: its own block removed, nothing else."""
    kept: list[str] = []
    inside = False
    for line in body.split("\n"):
        if line.strip() == AUTO_MARKER.strip():
            inside = True
            if kept and kept[-1].strip() == "":
                kept.pop()
            continue
        if inside:
            if HIDDEN_RE.match(line) or line.strip() == "":
                continue
            inside = False
        kept.append(line)
    return "\n".join(kept)


def _stripped(body: str) -> list[str]:
    """Every non-blank line that is neither a hidden link nor the block's own comment."""
    return [
        line.rstrip() for line in body.split("\n")
        if line.strip() and "[hidden]" not in line and "Auto-layout: spread elements" not in line
    ]


def _reoptimized(body: str) -> str:
    """The body as the optimizer would emit it now, from its pre-optimization state."""
    return ensure_puml_layout(_without_auto_block(body))


@pytest.mark.skipif(not BODIES, reason="no diagram corpus in this checkout")
@pytest.mark.parametrize("name,body", BODIES, ids=[n for n, _ in BODIES])
class TestNoStoredDiagramIsDisturbed:
    """The broadest negative: the optimizer only ever touches its own output.

    A generated block is refreshed on purpose — that is how a model change reflows the diagram
    it changed. Everything else on disk is somebody's authored layout: hand-placed hidden
    links, notations this module does not understand, diagrams with no groupings at all. None
    of it may move. If a layout change ever starts rewriting authored bodies, this says so.
    """

    def test_no_stored_body_is_rewritten_without_an_explicit_rebuild(
        self, name: str, body: str,
    ) -> None:
        """`ensure_puml_layout` must be inert over the whole corpus, generated bodies included.

        This is what stops an unrelated edit — a rename, a binding, a status change — from
        rearranging a diagram somebody laid out by hand. Only `rebuild_puml_layout` may.
        """
        assert ensure_puml_layout(body) == body, name

    def test_a_rebuild_only_ever_touches_the_generated_block(self, name: str, body: str) -> None:
        if AUTO_MARKER not in body:
            pytest.skip("nothing generated here to recompute")
        directive = re.compile(r"^\s*(top to bottom|left to right)\s+direction\s*$")

        relaid = rebuild_puml_layout(body)

        assert [line for line in _stripped(relaid) if not directive.match(line)] == \
               [line for line in _stripped(body) if not directive.match(line)], name

    def test_rebuild_is_idempotent_whatever_the_body(self, name: str, body: str) -> None:
        """Applies to every diagram: a second pass must be a fixed point."""
        once = rebuild_puml_layout(body)

        assert rebuild_puml_layout(once) == once, name



@pytest.mark.skipif(not GENERATED, reason="no generated diagrams in this checkout")
@pytest.mark.parametrize("name,body", GENERATED, ids=[n for n, _ in GENERATED])
class TestEveryGeneratedDiagram:
    def test_no_grouping_ends_up_with_a_backward_sequencing_edge(self, name: str, body: str) -> None:
        """The defect itself: an arrow that has to double back across its own grouping."""
        optimized = _reoptimized(body)
        pairs = _directed_pairs(optimized)

        for group in _parse_groupings(optimized):
            if len(group.aliases) < 2:
                continue
            chain = [HIDDEN_RE.match(line) for line in optimized.split("\n")]
            spread = [m for m in chain if m and m.group(1) in group.aliases]
            if not spread:
                continue
            order = [spread[0].group(1), *[m.group(2) for m in spread]]
            rank = {alias: index for index, alias in enumerate(order)}
            backward = [
                (source, target) for source, target in pairs
                if source in rank and target in rank and source != target and rank[source] > rank[target]
            ]
            assert backward == [], f"{name} [{group.label}] has backward edges: {backward}"

    def test_grouping_membership_is_preserved_exactly(self, name: str, body: str) -> None:
        """No element may be dropped, duplicated, or moved between groupings."""
        before = {g.label: sorted(g.aliases) for g in _parse_groupings(body)}
        after = {g.label: sorted(g.aliases) for g in _parse_groupings(_reoptimized(body))}

        assert after == before, name

    def test_flow_ordering_moves_nothing_but_hidden_links(self, name: str, body: str) -> None:
        """Compared against the optimizer with ordering disabled, not against what is stored.

        Some stored bodies predate the current direction-directive behaviour, so diffing
        against them would report drift this change did not cause. Running the same input
        through the optimizer twice — once ordering by flow, once in declaration order —
        isolates exactly what the ordering rule is responsible for.
        """
        source = _without_auto_block(body)
        with_ordering = ensure_puml_layout(source)
        with mock.patch.object(layout, "_flow_ordered", lambda aliases, _pairs: aliases):
            without_ordering = ensure_puml_layout(source)

        assert _stripped(with_ordering) == _stripped(without_ordering), name

    def test_the_constraint_count_is_unchanged(self, name: str, body: str) -> None:
        """Ordering must not buy its improvement with extra rank constraints."""
        source = _without_auto_block(body)
        with mock.patch.object(layout, "_flow_ordered", lambda aliases, _pairs: aliases):
            baseline = ensure_puml_layout(source)

        def hidden_links(text: str) -> int:
            return sum(1 for line in text.split("\n") if "[hidden]" in line)

        assert hidden_links(ensure_puml_layout(source)) == hidden_links(baseline), name

    def test_every_spread_chain_covers_its_grouping_once(self, name: str, body: str) -> None:
        optimized = _reoptimized(body)
        for group in _parse_groupings(optimized):
            if len(group.aliases) < 2:
                continue
            spread = [m for m in (HIDDEN_RE.match(line) for line in optimized.split("\n"))
                      if m and m.group(1) in group.aliases]
            if not spread:
                continue
            order = [spread[0].group(1), *[m.group(2) for m in spread]]
            assert sorted(order) == sorted(group.aliases), f"{name} [{group.label}]"

    def test_reoptimizing_is_idempotent(self, name: str, body: str) -> None:
        once = _reoptimized(body)

        assert ensure_puml_layout(once) == once, name


@pytest.mark.skipif(not BODIES, reason="no diagram corpus in this checkout")
class TestTheCorpusActuallyExercisesThis:
    """A green suite proves nothing if it ran over nothing."""

    def test_some_stored_diagram_carries_an_auto_layout_block(self) -> None:
        assert any("Auto-layout: spread elements" in body for _, body in BODIES)

    def test_some_grouping_contains_a_sequencing_edge(self) -> None:
        """Without one, the ordering rule above is never reached and proves nothing."""
        exercised = False
        for _, body in BODIES:
            pairs = _directed_pairs(body)
            for group in _parse_groupings(body):
                members = set(group.aliases)
                if len(members) >= 2 and any(s in members and t in members and s != t for s, t in pairs):
                    exercised = True
        assert exercised, "no grouping in the corpus has an internal flow to order"
