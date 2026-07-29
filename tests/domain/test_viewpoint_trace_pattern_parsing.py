"""Parse + serialize the trace-pattern grammar: the shipped production corpus round-trips
(domain → mapping → domain identity), and malformed declarations fail at load with the
stable typed error code."""

from __future__ import annotations

import pytest

from src.domain.viewpoints.viewpoint_trace_pattern_parsing import parse_trace_patterns
from src.domain.viewpoints.viewpoint_trace_pattern_serialization import trace_patterns_to_list
from src.domain.viewpoints.viewpoint_trace_patterns import (
    ERR_MISSING_FIELD,
    ERR_UNKNOWN_FIELD,
    ERR_UNKNOWN_KIND,
    ERR_UNKNOWN_VARIANT,
    TracePatternError,
)


def _motivation_branches() -> dict:
    return {
        "goal_to_outcome": {
            "kind": "stored-edge", "connection": "archimate-realization",
            "direction": "incoming", "endpoint": {"type": "outcome"},
        },
        "outcome_to_requirement": {
            "kind": "stored-edge", "connection": "archimate-realization",
            "direction": "incoming", "endpoint": {"type": "requirement"},
        },
    }


def _production_corpus() -> list[dict]:
    return [
        {
            "name": "motivation", "kind": "branch-complete-realization",
            "applies_to": ["goal", "outcome"], "branches": _motivation_branches(),
            "shortcuts": [
                {"kind": "diagnostic-edge", "connection": "archimate-influence",
                 "direction": "incoming", "endpoint": {"type": "requirement"}, "status": "shortcut"},
                {"kind": "diagnostic-edge", "connection": "archimate-association",
                 "direction": "incoming", "endpoint": {"type": "requirement"}, "status": "ambiguous_link"},
            ],
            "leaf": {"kind": "none"},
        },
        {
            "name": "overall_realization", "kind": "branch-complete-realization",
            "applies_to": ["goal", "outcome", "requirement"], "branches": {"ref": "motivation"},
            "leaf": {
                "kind": "derived-reachability", "connection": "archimate-realization",
                "traversal": "direct_and_derived", "max_hops": 4,
                "endpoint": {"registry": "permitted-realizers-of-requirement"},
            },
        },
        {
            "name": "behavior_coverage", "kind": "branch-complete-realization",
            "applies_to": ["goal", "outcome", "requirement"], "branches": {"ref": "motivation"},
            "diagnostic": True,
            "leaf": {
                "kind": "derived-reachability", "connection": "archimate-realization",
                "traversal": "direct_and_derived", "max_hops": 4,
                "endpoint": {"domain": "common", "class": "behavior-element"},
            },
        },
        {
            "name": "business_coverage", "kind": "branch-complete-realization",
            "applies_to": ["goal", "outcome", "requirement"], "branches": {"ref": "motivation"},
            "diagnostic": True,
            "leaf": {
                "kind": "derived-reachability", "connection": "archimate-realization",
                "traversal": "direct_and_derived", "max_hops": 4, "endpoint": {"domain": "business"},
            },
        },
    ]


class TestRoundTrip:
    def test_production_corpus_parses(self) -> None:
        parsed = parse_trace_patterns(_production_corpus(), label="vp")
        assert [p.name for p in parsed.patterns] == [
            "motivation", "overall_realization", "behavior_coverage", "business_coverage",
        ]
        assert parsed.by_name("overall_realization").branches.ref == "motivation"
        assert parsed.by_name("behavior_coverage").role == "diagnostic"
        assert parsed.by_name("motivation").role == "authoritative"

    def test_domain_mapping_domain_is_identity(self) -> None:
        once = parse_trace_patterns(_production_corpus(), label="vp")
        twice = parse_trace_patterns(trace_patterns_to_list(once), label="vp")
        assert once == twice

    def test_ref_is_preserved_not_expanded_on_serialize(self) -> None:
        serialized = trace_patterns_to_list(parse_trace_patterns(_production_corpus(), label="vp"))
        overall = next(p for p in serialized if p["name"] == "overall_realization")
        assert overall["branches"] == {"ref": "motivation"}


class TestNegativePaths:
    @pytest.mark.parametrize(
        "mutate,expected_code",
        [
            (lambda p: {**p, "kind": "reachability"}, ERR_UNKNOWN_KIND),
            (lambda p: {**p, "surprise": 1}, ERR_UNKNOWN_FIELD),
            (lambda p: {k: v for k, v in p.items() if k != "applies_to"}, ERR_MISSING_FIELD),
        ],
    )
    def test_malformed_pattern_raises_typed_code(self, mutate, expected_code) -> None:
        corpus = _production_corpus()
        corpus[0] = mutate(corpus[0])
        with pytest.raises(TracePatternError) as exc:
            parse_trace_patterns(corpus, label="vp")
        assert exc.value.code == expected_code

    def test_unknown_edge_variant_in_branches_rejected(self) -> None:
        corpus = _production_corpus()
        corpus[0]["branches"]["goal_to_outcome"]["kind"] = "diagnostic-edge"
        with pytest.raises(TracePatternError) as exc:
            parse_trace_patterns(corpus, label="vp")
        assert exc.value.code == ERR_UNKNOWN_VARIANT

    def test_unknown_leaf_endpoint_target_rejected(self) -> None:
        corpus = _production_corpus()
        corpus[1]["leaf"]["endpoint"] = {"type": "requirement"}
        with pytest.raises(TracePatternError) as exc:
            parse_trace_patterns(corpus, label="vp")
        assert exc.value.code == ERR_UNKNOWN_FIELD  # 'type' is not an accepted leaf-endpoint key
