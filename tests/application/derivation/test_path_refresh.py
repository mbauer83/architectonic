"""Tests for path-projection diff refresh and verifier E409/E410.

Property tests (idempotence, determinism) + unit tests for drifted/broken classification.
"""

from __future__ import annotations

from pathlib import Path

from src.application.derivation.refresh import (
    SelectionDelta,
    _is_path_well_formed,
    _parse_path_key,
    apply_selection_delta,
    compute_derivation_diff,
)
from src.application.derivation.strategy_registry import DerivationStrategyCatalog, DerivationStrategyCatalogBuilder
from src.application.derivation.types import CandidateSet
from src.application.verification._verifier_rules_binding_targets import (
    _check_connection_path_target,
)
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.relationships.derivation_types import StrategySpec
from src.domain.viewpoints.view_derivations import DerivationSelection, SourceModelSnapshot, ViewDerivation
from tests.application.derivation._fixtures import FakeQuery, _connection, _entity


def _path_catalog(derive_fn) -> DerivationStrategyCatalog:
    b = DerivationStrategyCatalogBuilder()
    b.register(StrategySpec(name="path-projection", version=1, supported_filters=frozenset()), derive_fn)
    return b.build()

# ---------------------------------------------------------------------------
# Path key helpers
# ---------------------------------------------------------------------------


def test_parse_path_key_basic() -> None:
    steps = _parse_path_key("A---B@@serving@fwd|B---C@@flow@rev")
    assert steps == [("A---B@@serving", False), ("B---C@@flow", True)]


def test_parse_path_key_single() -> None:
    assert _parse_path_key("X---Y@@t@fwd") == [("X---Y@@t", False)]


def test_is_path_well_formed_all_present() -> None:
    known = {"A---B@@s", "B---C@@s"}
    assert _is_path_well_formed("A---B@@s@fwd|B---C@@s@fwd", known) is True


def test_is_path_well_formed_missing_step() -> None:
    known = {"A---B@@s"}
    assert _is_path_well_formed("A---B@@s@fwd|B---C@@s@fwd", known) is False


# ---------------------------------------------------------------------------
# Verifier E409 / E410
# ---------------------------------------------------------------------------


def _result() -> VerificationResult:
    return VerificationResult(path=Path("/fake"), file_type="diagram", issues=[])


def test_e409_step_not_in_scope() -> None:
    allowed = {"A---B@@s"}
    result = _result()
    _check_connection_path_target("bind1", [{"id": "MISSING@@s"}], allowed, result, "test")
    codes = [i.code for i in result.issues]
    assert "E409" in codes


def test_e410_chain_not_contiguous() -> None:
    # A---B and C---D are not contiguous (B ≠ C)
    allowed = {"A---B@@s", "C---D@@s"}
    result = _result()
    _check_connection_path_target(
        "bind1",
        [{"id": "A---B@@s"}, {"id": "C---D@@s"}],
        allowed, result, "test",
    )
    codes = [i.code for i in result.issues]
    assert "E410" in codes


def test_no_error_valid_chain() -> None:
    # A---B---C: step 1 to=B, step 2 from=B ✓
    allowed = {"A---B@@s", "B---C@@s"}
    result = _result()
    _check_connection_path_target(
        "bind1",
        [{"id": "A---B@@s"}, {"id": "B---C@@s"}],
        allowed, result, "test",
    )
    assert result.issues == []


def test_reversed_chain_valid() -> None:
    # A---B reversed (from=B, to=A), then A---C (from=A, to=C) ✓
    allowed = {"A---B@@s", "A---C@@s"}
    result = _result()
    _check_connection_path_target(
        "bind1",
        [{"id": "A---B@@s", "reversed": True}, {"id": "A---C@@s"}],
        allowed, result, "test",
    )
    assert result.issues == []


# ---------------------------------------------------------------------------
# Diff: drifted vs broken path classification
# ---------------------------------------------------------------------------


def _make_vd(
    strategy: str = "path-projection",
    version: int = 1,
    included_paths: tuple[str, ...] = (),
) -> ViewDerivation:
    return ViewDerivation(
        id="vd1",
        strategy=strategy,
        strategy_version=version,
        source_model_snapshot=SourceModelSnapshot(repo_scope="both"),
        selection=DerivationSelection(included_paths=included_paths) if included_paths else None,
    )


def test_new_path_appears_in_diff(tmp_path: Path) -> None:
    diag = tmp_path / "d.puml"
    diag.write_text("---\nbindings: []\n---\n")

    a = _entity("A")
    b = _entity("B")
    ab = _connection("A---B@@serving", "A", "B")
    query = FakeQuery([a, b], [ab])

    catalog = _path_catalog(lambda params, snap, q: CandidateSet(paths=frozenset(["A---B@@serving@fwd"])))
    vd = _make_vd(included_paths=())
    diff = compute_derivation_diff(diag, {}, vd, query, catalog)
    assert "A---B@@serving@fwd" in diff.new_paths
    assert diff.gone_paths == []


def test_gone_path_broken_when_conn_missing(tmp_path: Path) -> None:
    diag = tmp_path / "d.puml"
    diag.write_text("---\nbindings: []\n---\n")

    # Query has NO connections — path ids are unknown → broken
    query = FakeQuery([], [])

    catalog = _path_catalog(lambda params, snap, q: CandidateSet(paths=frozenset()))
    vd = _make_vd(included_paths=("A---B@@s@fwd|B---C@@s@fwd",))
    diff = compute_derivation_diff(diag, {}, vd, query, catalog)

    assert "A---B@@s@fwd|B---C@@s@fwd" in diff.broken_paths
    assert diff.drifted_paths == []


def test_gone_path_drifted_when_conns_present(tmp_path: Path) -> None:
    diag = tmp_path / "d.puml"
    diag.write_text("---\nbindings: []\n---\n")

    ab = _connection("A---B@@s", "A", "B")
    bc = _connection("B---C@@s", "B", "C")
    query = FakeQuery([], [ab, bc])

    catalog = _path_catalog(lambda params, snap, q: CandidateSet(paths=frozenset()))
    pk = "A---B@@s@fwd|B---C@@s@fwd"
    vd = _make_vd(included_paths=(pk,))
    diff = compute_derivation_diff(diag, {}, vd, query, catalog)

    assert pk in diff.drifted_paths
    assert diff.broken_paths == []


# ---------------------------------------------------------------------------
# Idempotence property: unchanged model + same selection → empty diff
# ---------------------------------------------------------------------------


def test_refresh_idempotent_no_change(tmp_path: Path) -> None:
    diag = tmp_path / "d.puml"
    diag.write_text("---\nbindings: []\n---\n")

    pk = "A---B@@serving@fwd"
    catalog = _path_catalog(lambda params, snap, q: CandidateSet(paths=frozenset([pk])))
    query = FakeQuery([], [_connection("A---B@@serving", "A", "B")])
    vd = _make_vd(included_paths=(pk,))
    diff = compute_derivation_diff(diag, {}, vd, query, catalog)

    assert diff.new_paths == []
    assert diff.gone_paths == []
    assert diff.drifted_paths == []
    assert diff.broken_paths == []


# ---------------------------------------------------------------------------
# apply_selection_delta: paths
# ---------------------------------------------------------------------------


def test_apply_delta_adds_included_path() -> None:
    raw_vds = [{"id": "vd1", "strategy": "path-projection", "strategy_version": 1,
                "source_model_snapshot": {"repo_scope": "both"}}]
    delta = SelectionDelta(add_included_paths=["A---B@@s@fwd"])
    updated = apply_selection_delta(raw_vds, "vd1", delta)
    sel = updated[0].get("selection", {})
    assert "A---B@@s@fwd" in sel.get("included_paths", [])


def test_apply_delta_removes_included_path() -> None:
    raw_vds = [{
        "id": "vd1", "strategy": "path-projection", "strategy_version": 1,
        "source_model_snapshot": {"repo_scope": "both"},
        "selection": {"included_paths": ["A---B@@s@fwd", "B---C@@s@fwd"]},
    }]
    delta = SelectionDelta(remove_included_paths=["A---B@@s@fwd"])
    updated = apply_selection_delta(raw_vds, "vd1", delta)
    paths = updated[0]["selection"]["included_paths"]  # type: ignore[index]
    assert "A---B@@s@fwd" not in paths
    assert "B---C@@s@fwd" in paths


def test_apply_delta_adds_excluded_path() -> None:
    raw_vds = [{"id": "vd1", "strategy": "path-projection", "strategy_version": 1,
                "source_model_snapshot": {"repo_scope": "both"}}]
    delta = SelectionDelta(add_excluded_paths=["X---Y@@s@fwd"])
    updated = apply_selection_delta(raw_vds, "vd1", delta)
    sel = updated[0].get("selection", {})
    assert "X---Y@@s@fwd" in sel.get("excluded_paths", [])
