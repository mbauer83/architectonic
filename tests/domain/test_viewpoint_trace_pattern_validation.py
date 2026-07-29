"""Cross-pattern validation + {ref} expansion: name uniqueness, structural caps at limit and
limit+1, and reference integrity (dangling / cyclic / depth)."""

from __future__ import annotations

import dataclasses

import pytest

from src.domain.viewpoints.viewpoint_trace_pattern_validation import expand_branch_edges, validate_trace_patterns
from src.domain.viewpoints.viewpoint_trace_patterns import (
    ERR_CYCLIC_REF,
    ERR_DANGLING_REF,
    MAX_EDGE_DECLARATIONS,
    MAX_TRACE_PATTERNS,
    BranchesRef,
    DiagnosticEdge,
    InlineBranches,
    NamedBranchEdge,
    StoredEdge,
    TracePattern,
    TracePatternError,
    TracePatternSet,
)


def _edge(label: str) -> NamedBranchEdge:
    return NamedBranchEdge(label, StoredEdge("archimate-realization", "incoming", "outcome"))


def _inline(name: str, *labels: str) -> TracePattern:
    return TracePattern(name=name, applies_to=("goal",), branches=InlineBranches(tuple(_edge(x) for x in labels)))


def _ref(name: str, ref: str) -> TracePattern:
    return TracePattern(name=name, applies_to=("goal",), branches=BranchesRef(ref))


def _codes(issues) -> list[str]:
    return [i.code for i in issues]


class TestExpansion:
    def test_ref_expands_to_referents_branch_edges(self) -> None:
        base = _inline("motivation", "a", "b")
        overall = _ref("overall", "motivation")
        edges = expand_branch_edges(overall, TracePatternSet((base, overall)))
        assert [e.label for e in edges] == ["a", "b"]

    def test_dangling_ref_raises(self) -> None:
        overall = _ref("overall", "nope")
        with pytest.raises(TracePatternError) as exc:
            expand_branch_edges(overall, TracePatternSet((overall,)))
        assert exc.value.code == ERR_DANGLING_REF

    def test_direct_cycle_raises(self) -> None:
        a = _ref("a", "a")
        with pytest.raises(TracePatternError) as exc:
            expand_branch_edges(a, TracePatternSet((a,)))
        assert exc.value.code == ERR_CYCLIC_REF

    def test_mutual_cycle_raises(self) -> None:
        a, b = _ref("a", "b"), _ref("b", "a")
        with pytest.raises(TracePatternError) as exc:
            expand_branch_edges(a, TracePatternSet((a, b)))
        assert exc.value.code == ERR_CYCLIC_REF


class TestValidation:
    def test_clean_set_has_no_issues(self) -> None:
        base = _inline("motivation", "a", "b")
        overall = _ref("overall", "motivation")
        assert validate_trace_patterns(TracePatternSet((base, overall)), path="q", check_ergonomics=True) == []

    def test_duplicate_name_reported(self) -> None:
        issues = validate_trace_patterns(
            TracePatternSet((_inline("m", "a"), _inline("m", "b"))), path="q", check_ergonomics=True
        )
        assert "trace-pattern-duplicate-name" in _codes(issues)

    def test_empty_applies_to_reported(self) -> None:
        bad = dataclasses.replace(_inline("m", "a"), applies_to=())
        issues = validate_trace_patterns(TracePatternSet((bad,)), path="q", check_ergonomics=True)
        assert "trace-pattern-empty-applies-to" in _codes(issues)

    def test_dangling_ref_surfaces_as_issue_not_exception(self) -> None:
        issues = validate_trace_patterns(TracePatternSet((_ref("overall", "nope"),)), path="q", check_ergonomics=True)
        assert ERR_DANGLING_REF in _codes(issues)

    def test_pattern_count_at_cap_ok_over_cap_flagged(self) -> None:
        at_cap = TracePatternSet(tuple(_inline(f"p{i}", "a") for i in range(MAX_TRACE_PATTERNS)))
        assert "trace-pattern-count-exceeded" not in _codes(
            validate_trace_patterns(at_cap, path="q", check_ergonomics=True)
        )
        over = TracePatternSet(tuple(_inline(f"p{i}", "a") for i in range(MAX_TRACE_PATTERNS + 1)))
        assert "trace-pattern-count-exceeded" in _codes(validate_trace_patterns(over, path="q", check_ergonomics=True))

    def test_edge_count_over_cap_flagged_after_expansion(self) -> None:
        labels = [f"e{i}" for i in range(MAX_EDGE_DECLARATIONS)]
        base = _inline("motivation", *labels)  # MAX_EDGE_DECLARATIONS branch edges
        # overall refs motivation (same edge count) + one shortcut → over the cap after expansion
        overall = dataclasses.replace(
            _ref("overall", "motivation"),
            shortcuts=(DiagnosticEdge("archimate-influence", "incoming", "requirement", "shortcut"),),
        )
        issues = validate_trace_patterns(TracePatternSet((base, overall)), path="q", check_ergonomics=True)
        assert "trace-pattern-edge-count-exceeded" in _codes(issues)

    def test_caps_skipped_when_ergonomics_off(self) -> None:
        over = TracePatternSet(tuple(_inline(f"p{i}", "a") for i in range(MAX_TRACE_PATTERNS + 1)))
        assert "trace-pattern-count-exceeded" not in _codes(
            validate_trace_patterns(over, path="q", check_ergonomics=False)
        )
