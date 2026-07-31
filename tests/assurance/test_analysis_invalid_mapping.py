"""Every ``AnalysisInvalid`` the use cases can construct has an HTTP mapping, and the right one.

``AnalysisInvalid`` carries a free-form string, and both assurance routers used to put it on the wire
verbatim with status 400. That published five codes the closed ``ErrorCode`` union never declared, and
gave two of them the wrong status: an analysis that authored nodes is a state conflict (409), not a
malformed request, and a missing group is a 404.

The mapping is exhaustive by construction *only* if something counts. So this extracts the codes from
the application source and compares them against the table: a sixth code added to a use case fails
here rather than reaching a client as an undeclared string with a misleading status.
"""

from __future__ import annotations

import ast
import pathlib

from src.application.assurance_analysis import AnalysisInvalid
from src.application.assurance_model_bind import BindInvalid
from src.infrastructure.gui.contracts.errors import ERROR_DETAIL_TYPES
from src.infrastructure.gui.routers._assurance_invalid import (
    _BIND_MAPPING,
    _MAPPING,
    bind_invalid_as_api_error,
    invalid_as_api_error,
)

_APPLICATION = pathlib.Path(__file__).resolve().parents[2] / "src" / "application"


def _constructed_codes(result_type: str = "AnalysisInvalid") -> set[str]:
    """Every literal first argument to a ``<result_type>(...)`` call in the application layer."""
    codes: set[str] = set()
    for path in _APPLICATION.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            callee = node.func
            name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", "")
            if name != result_type or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                codes.add(first.value)
    return codes


def test_the_extraction_finds_the_codes_at_all() -> None:
    """Guards the guard: an extraction that found nothing would satisfy every assertion below."""
    assert _constructed_codes(), "no AnalysisInvalid codes found — the extraction is broken"


def test_every_constructed_code_is_mapped() -> None:
    unmapped = sorted(_constructed_codes() - set(_MAPPING))
    assert unmapped == [], (
        f"these reach a client with no declared mapping: {unmapped}. Add them to _MAPPING with a code "
        "from the closed ErrorCode vocabulary and the status that describes the failure."
    )


def test_the_table_maps_nothing_the_use_cases_cannot_produce() -> None:
    """The other direction, so the table stays a description rather than a wish list."""
    extra = sorted(set(_MAPPING) - _constructed_codes())
    assert extra == [], f"mapped but never constructed: {extra}"


def test_every_mapped_code_is_in_the_closed_vocabulary() -> None:
    """The point of the exercise: nothing escapes the published union."""
    for source, (_status, code) in sorted(_MAPPING.items()):
        assert code in ERROR_DETAIL_TYPES, f"{source} maps to undeclared code {code!r}"


def test_a_state_conflict_is_a_409_not_a_400() -> None:
    """An analysis that authored nodes is not a malformed request — nothing the caller sent is wrong,
    and 400 tells them to go and fix it. The plan assigns this 409."""
    error = invalid_as_api_error(
        AnalysisInvalid("analysis_not_empty", "authored 3", subject="STPA@1", count=3)
    )

    assert error.status_code == 409
    assert error.code == "analysis_not_empty"
    # The details carry the structured context the message states in prose, so a client does not parse
    # a sentence to learn how many nodes stand in the way.
    assert error.details is not None
    assert error.details.analysis_id == "STPA@1"  # type: ignore[union-attr]
    assert error.details.authored_node_count == 3  # type: ignore[union-attr]


def test_a_missing_group_is_a_404() -> None:
    error = invalid_as_api_error(AnalysisInvalid("group_not_found", "no such group"))

    assert error.status_code == 404
    assert error.code == "not_found"


def test_a_rejected_value_carries_the_field_it_was_about() -> None:
    """`validation_error` is the generic case, so the field path is what makes it actionable — a client
    highlighting the wrong input is worse than one highlighting none."""
    error = invalid_as_api_error(AnalysisInvalid("invalid_method", "method must be one of ..."))

    assert error.status_code == 422
    assert error.code == "validation_error"
    assert error.details is not None
    assert error.details.field_errors[0].field == "method"  # type: ignore[union-attr]


def test_every_bind_code_is_mapped_too() -> None:
    """The bind use case has its own invalid result, and it had the same defect: one of its two codes
    was a 400 for a state the caller could not have known about."""
    constructed = _constructed_codes("BindInvalid")
    assert constructed, "no BindInvalid codes found — the extraction is broken"
    assert sorted(constructed) == sorted(_BIND_MAPPING), (
        f"constructed {sorted(constructed)} but mapped {sorted(_BIND_MAPPING)}"
    )
    for _source, (_status, code) in sorted(_BIND_MAPPING.items()):
        assert code in ERROR_DETAIL_TYPES


def test_a_wrong_binding_state_is_a_conflict_not_a_bad_request() -> None:
    error = bind_invalid_as_api_error(
        BindInvalid("invalid_binding_status", "node is 'bound'")
    )

    assert error.status_code == 409
    assert error.code == "conflict"


def test_an_unknown_architecture_type_is_a_rejected_value() -> None:
    error = bind_invalid_as_api_error(BindInvalid("unknown_arch_type", "Unknown type: 'widget'"))

    assert error.status_code == 422
    assert error.code == "validation_error"
    assert error.details is not None
    assert error.details.field_errors[0].field == "suggested_arch_type"  # type: ignore[union-attr]
