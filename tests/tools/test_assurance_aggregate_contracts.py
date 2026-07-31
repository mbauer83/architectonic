"""The four assurance aggregate contracts, held against the functions that produce them.

Third instance of one lesson: a DTO written from a guess rather than from the producer is a closed model
that rejects every real response. `DocumentReference` made `GET /api/entities/{id}` answer 500 that way.
So stats, coverage, the risk register and verification each get their field sets compared against the
dict literals the application layer actually returns.

The comparison reads the producers' *source*. Calling them needs an unlocked SQLCipher store populated
into a particular shape, and the question here is which keys the code can emit — a property of the code,
not of a fixture.
"""

from __future__ import annotations

import ast
import pathlib

from src.infrastructure.gui.contracts.assurance_queries import (
    AssuranceCoverageGaps,
    AssuranceCoverageResponse,
    AssuranceNodeRef,
    AssuranceRiskRegisterResponse,
    AssuranceRiskRow,
    AssuranceStatsResponse,
    AssuranceVerificationIssue,
    AssuranceVerifyResponse,
)

_SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "application"
_QUERIES = _SRC / "assurance_queries.py"
_EXPOSURE = _SRC / "assurance_exposure.py"
_VERIFIER = _SRC / "verification" / "assurance_verifier.py"


def _function(path: pathlib.Path, name: str) -> ast.AST:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {path.name} — the producer moved or was renamed")


def _keys(node: ast.Dict) -> frozenset[str]:
    return frozenset(
        k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)
    )


def _returned_keys(path: pathlib.Path, name: str) -> frozenset[str]:
    """The keys of the dict this function returns."""
    for node in ast.walk(_function(path, name)):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            return _keys(node.value)
    raise AssertionError(f"{name} no longer returns a dict literal")


def _dict_literals(path: pathlib.Path, name: str) -> list[frozenset[str]]:
    """Every dict literal inside this function, as its key set."""
    return [
        _keys(node) for node in ast.walk(_function(path, name)) if isinstance(node, ast.Dict)
    ]


def _fields(model: type) -> set[str]:
    return set(model.model_fields)  # type: ignore[attr-defined]


# ── stats ─────────────────────────────────────────────────────────────────────

def test_the_stats_contract_matches_what_redact_stats_returns() -> None:
    assert _returned_keys(_EXPOSURE, "redact_stats") == _fields(AssuranceStatsResponse)


# ── coverage ──────────────────────────────────────────────────────────────────

def test_the_coverage_envelope_matches_what_coverage_gaps_returns() -> None:
    assert _returned_keys(_QUERIES, "coverage_gaps") == _fields(AssuranceCoverageResponse)


def test_every_gap_category_the_producer_builds_is_a_declared_field() -> None:
    """Both directions, because the categories are named fields rather than an open map: a ninth
    category added to the producer would fail its own response, and a field no category fills would be
    a promise nothing keeps."""
    categories = _fields(AssuranceCoverageGaps)
    literals = _dict_literals(_QUERIES, "coverage_gaps")
    built = next((keys for keys in literals if keys & categories), frozenset())
    assert built == categories, (
        f"producer builds {sorted(built)}, contract declares {sorted(categories)}"
    )


def test_a_gap_entry_carries_exactly_the_node_reference_fields() -> None:
    """Every category's entries come from one of three comprehensions in that function, and all three
    build the same two-key shape. If one grows a key, this is what says so."""
    declared = _fields(AssuranceNodeRef)
    entry_shapes = [
        keys for keys in _dict_literals(_QUERIES, "coverage_gaps") if "node_id" in keys
    ]
    assert entry_shapes, "no node-reference literal found — the extraction stopped working"
    for shape in entry_shapes:
        assert shape == declared, f"entry emits {sorted(shape)}, contract declares {sorted(declared)}"


# ── risk register ─────────────────────────────────────────────────────────────

def test_the_register_envelope_matches_what_risk_register_returns() -> None:
    assert _returned_keys(_QUERIES, "risk_register") == _fields(AssuranceRiskRegisterResponse)


def test_a_risk_row_matches_the_row_the_producer_appends() -> None:
    declared = _fields(AssuranceRiskRow)
    rows = [keys for keys in _dict_literals(_QUERIES, "risk_register") if "treatment" in keys]
    assert len(rows) == 1, "expected one appended row literal in risk_register"
    assert rows[0] == declared, f"producer emits {sorted(rows[0])}, contract declares {sorted(declared)}"


# ── verification ──────────────────────────────────────────────────────────────

def test_the_verify_contract_is_format_result_plus_the_exposure_flag() -> None:
    """The route adds exactly one key to the serialised result. Anything else it added would be
    undocumented, and anything the producer emits that the DTO omits would be rejected."""
    assert _returned_keys(_VERIFIER, "format_result") | {"visibility_limited"} == _fields(
        AssuranceVerifyResponse
    )


def test_an_issue_matches_the_issue_the_producer_serialises() -> None:
    declared = _fields(AssuranceVerificationIssue)
    issues = [keys for keys in _dict_literals(_VERIFIER, "format_result") if "severity" in keys]
    assert len(issues) == 1, "expected one issue literal in format_result"
    assert issues[0] == declared, (
        f"producer emits {sorted(issues[0])}, contract declares {sorted(declared)}"
    )


def test_the_severity_values_the_result_partitions_on_are_the_permitted_ones() -> None:
    """`valid`, `error_count`, `warning_count` and `info_count` are each a filter on one severity
    string. A fifth severity added to the domain and not to this literal would arrive as a value no
    count includes and no client can render."""
    from src.application.verification import assurance_issues

    source = pathlib.Path(assurance_issues.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    partitioned = {
        node.comparators[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Attribute)
        and node.left.attr == "severity"
        and isinstance(node.comparators[0], ast.Constant)
    }
    permitted = set(AssuranceVerificationIssue.model_fields["severity"].annotation.__args__)  # type: ignore[union-attr]
    assert partitioned == permitted, (
        f"result partitions on {sorted(partitioned)}, contract permits {sorted(permitted)}"
    )
