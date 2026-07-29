"""Property/validation tests for the meta-ontology formalizations F1–F4.

Each formalization states a law the registry must satisfy; this file is where those laws are
checked against the real registry rather than against a fixture.

F1 — Signature + instance typing: startup_validation.py implements the fibration check;
     this file adds a real-registry integration test.
F2 — Bridge morphism with class preservation: test_bridges.py has per-rule unit tests;
     this file asserts the real C4 bridges satisfy the law against the live registry.
F3 — Bindings as constrained relation: test_verifier_bindings.py has per-rule tests;
     this file asserts the key structural invariants hold.
F4 — Derivation as pure function (hypothesis property tests):
     determinism, refresh idempotence, selection monotonicity, no silent mutation.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from src.application.derivation.explicit_selection import SPEC as ES_SPEC
from src.application.derivation.explicit_selection import derive as es_derive
from src.application.derivation.refresh import compute_derivation_diff
from src.application.derivation.strategy_registry import DerivationStrategyCatalog, DerivationStrategyCatalogBuilder
from src.application.verification._verifier_rules_bindings import check_bindings_scoped
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.viewpoints.view_derivations import DerivationSelection, SourceModelSnapshot, ViewDerivation
from tests.application.derivation._fixtures import FakeQuery, _entity


def _build_es_catalog() -> DerivationStrategyCatalog:
    b = DerivationStrategyCatalogBuilder()
    b.register(ES_SPEC, es_derive)
    return b.build()


_ES_CATALOG = _build_es_catalog()

_SNAPSHOT = SourceModelSnapshot(repo_scope="both")
_ENTITY_ID = "APP@1000000000.AbcDef.my-app"


# ── Hypothesis composite strategies ──────────────────────────────────────────


@st.composite
def _entity_model(draw: st.DrawFn) -> tuple[list[str], list[str], list[str]]:
    """Draw (all_ids, selected_ids, excluded_ids) with selected ∩ excluded = ∅."""
    n = draw(st.integers(min_value=0, max_value=7))
    all_ids = [f"ent_{i}" for i in range(n)]
    if not all_ids:
        return all_ids, [], []
    labels = draw(
        st.lists(st.sampled_from(["sel", "exc", "none"]), min_size=n, max_size=n)
    )
    return (
        all_ids,
        [e for e, lb in zip(all_ids, labels) if lb == "sel"],
        [e for e, lb in zip(all_ids, labels) if lb == "exc"],
    )


def _make_vd(
    all_ids: list[str],
    selected: list[str],
    excluded: list[str],
    vd_id: str = "d1",
) -> ViewDerivation:
    sel = (
        DerivationSelection(
            included_entity_ids=tuple(selected),
            excluded_entity_ids=tuple(excluded),
        )
        if selected or excluded
        else None
    )
    return ViewDerivation(
        id=vd_id,
        strategy="explicit-selection",
        strategy_version=1,
        source_model_snapshot=_SNAPSHOT,
        parameters={"entity_ids": all_ids},
        selection=sel,
    )


def _tmp_diagram_file() -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".puml", delete=False)
    f.write("dummy")
    f.close()
    return Path(f.name)


@pytest.fixture(scope="module")
def dummy_diagram() -> Iterator[Path]:
    """One reusable on-disk diagram file for the F4 property tests.

    The file content is irrelevant (``compute_revision`` only hashes it), so a single
    file is shared across all Hypothesis examples instead of being created and unlinked
    per example — this removes per-example filesystem IO from the property loop.
    """
    path = _tmp_diagram_file()
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


# ── F1: Signature + instance typing ──────────────────────────────────────────


class TestF1SignatureTyping:
    """F1: every artifact type resolves in Σ* (the combined module registry).

    Property: an unknown type causes startup_validation to abort and report the
    offending type name and artifact id.
    Per-rule unit tests live in tests/common/test_startup_validation.py.
    """

    def _make_repo(self, entity: object) -> object:
        class _Repo:
            def list_entities(self, **_):  # type: ignore[no-untyped-def]
                return [entity]

            def list_connections(self, **_):  # type: ignore[no-untyped-def]
                return []

            def list_diagrams(self, **_):  # type: ignore[no-untyped-def]
                return []

            @property
            def repo_roots(self) -> list[Path]:
                return []

        return _Repo()

    def test_unknown_entity_type_aborts_with_id(self) -> None:
        from src.application.startup_validation import (  # noqa: PLC0415
            RepoCompatibilityError,
            validate_repo_compatibility,
        )
        from src.infrastructure.app_bootstrap import build_module_registry  # noqa: PLC0415

        reg = build_module_registry()
        entity = _entity("FAKE@9999999999.AbcDef.test", "__f1_unknown_type__")
        with pytest.raises(RepoCompatibilityError) as exc:
            validate_repo_compatibility(self._make_repo(entity), reg)  # type: ignore[arg-type]
        assert "__f1_unknown_type__" in exc.value.errors[0]
        assert "FAKE@9999999999.AbcDef.test" in exc.value.errors[0]

    def test_real_registry_accepts_known_archimate_types(self) -> None:
        from src.application.startup_validation import validate_repo_compatibility  # noqa: PLC0415
        from src.infrastructure.app_bootstrap import build_module_registry  # noqa: PLC0415

        reg = build_module_registry()
        entity = _entity("APP@1234567890.AbcDef.my-app", "application-component")
        validate_repo_compatibility(self._make_repo(entity), reg)  # type: ignore[arg-type]


# ── F2: Bridge morphism with class preservation ───────────────────────────────


class TestF2BridgeMorphism:
    """F2: preservation law ∀ c ∈ preserves_classes, ∀ t ∈ β(x): c ∈ classes(t).

    Per-rule unit tests (coherent/violated fixtures) live in tests/domain/test_bridges.py.
    This class asserts the law holds for the real C4 registry.
    """

    def test_real_c4_bridges_satisfy_class_preservation(self) -> None:
        from src.application.startup_validation import validate_registry_consistency  # noqa: PLC0415
        from src.infrastructure.app_bootstrap import build_module_registry  # noqa: PLC0415

        reg = build_module_registry()
        validate_registry_consistency(reg)  # raises RegistryConsistencyError on any violation


# ── F3: Bindings as constrained relation ──────────────────────────────────────


class TestF3BindingConstraints:
    """F3: binding set Bnd satisfies all declared constraints (E401–E408).

    Per-rule unit tests live in tests/tools/test_verifier_bindings.py.
    This class asserts the two most structural invariants: subject resolution (E401)
    and at-most-one diagram-level scoped-by (E405).
    """

    def _run(self, fm: dict) -> VerificationResult:
        r = VerificationResult(path=Path("/test/d.puml"), file_type="diagram")
        check_bindings_scoped(
            fm,
            file_scope="engagement",
            allowed_entities={_ENTITY_ID},
            allowed_connections=set(),
            all_entities={_ENTITY_ID},
            all_connections=set(),
            result=r,
            loc="/test/d.puml",
        )
        return r

    def test_dangling_subject_element_fails_e401(self) -> None:
        fm = {
            "diagram-entities": {"container": []},
            "bindings": [{
                "id": "b1",
                "subject": {"kind": "entity", "id": "ghost"},
                "correspondence_kind": "represents",
                "target": {"entity_id": _ENTITY_ID},
            }],
        }
        codes = {i.code for i in self._run(fm).issues if i.severity == "error"}
        assert "E401" in codes

    def test_two_diagram_scoped_by_fails_e405(self) -> None:
        fm = {
            "diagram-entities": {},
            "bindings": [
                {
                    "id": "b1",
                    "subject": {"kind": "diagram"},
                    "correspondence_kind": "scoped-by",
                    "target": {"entity_id": _ENTITY_ID},
                },
                {
                    "id": "b2",
                    "subject": {"kind": "diagram"},
                    "correspondence_kind": "scoped-by",
                    "target": {"entity_id": _ENTITY_ID},
                },
            ],
        }
        codes = {i.code for i in self._run(fm).issues if i.severity == "error"}
        assert "E405" in codes

    def test_clean_represents_binding_passes(self) -> None:
        fm = {
            "diagram-entities": {"container": [{"id": "box1", "label": "App"}]},
            "bindings": [{
                "id": "b1",
                "subject": {"kind": "entity", "id": "box1"},
                "correspondence_kind": "represents",
                "target": {"entity_id": _ENTITY_ID},
            }],
        }
        assert self._run(fm).valid


# ── F4: Derivation as pure function (hypothesis property tests) ───────────────


class TestF4DerivationPurity:
    """F4 property tests: determinism, refresh idempotence, selection monotonicity, no-mutation.

    Uses hypothesis to drive the explicit-selection/v1 strategy over arbitrary model states.
    """

    @given(_entity_model())
    @settings(max_examples=150, deadline=None)
    def test_f4_determinism(
        self, model_data: tuple[list[str], list[str], list[str]]
    ) -> None:
        """F_θ(M) == F_θ(M): calling the strategy twice yields identical CandidateSets."""
        all_ids, selected, _ = model_data
        query = FakeQuery(entities=[_entity(eid) for eid in all_ids])
        params: dict[str, object] = {"entity_ids": selected}
        assert es_derive(params, _SNAPSHOT, query) == es_derive(params, _SNAPSHOT, query)

    @given(_entity_model())
    @settings(max_examples=150, deadline=None)
    def test_f4_refresh_idempotence(
        self, dummy_diagram: Path, model_data: tuple[list[str], list[str], list[str]]
    ) -> None:
        """If M is unchanged and all candidates are already included, Refresh yields empty diff."""
        all_ids, selected, _ = model_data
        query = FakeQuery(entities=[_entity(eid) for eid in all_ids])
        candidates = es_derive({"entity_ids": selected}, _SNAPSHOT, query)
        vd = ViewDerivation(
            id="d1",
            strategy="explicit-selection",
            strategy_version=1,
            source_model_snapshot=_SNAPSHOT,
            parameters={"entity_ids": selected},
            selection=DerivationSelection(
                included_entity_ids=tuple(sorted(candidates.entity_ids)),
            ),
        )
        diff = compute_derivation_diff(dummy_diagram, {}, vd, query, _ES_CATALOG)
        assert diff.is_empty, f"new={diff.new_entity_ids}, gone={diff.gone_entity_ids}"

    @given(_entity_model())
    @settings(max_examples=150, deadline=None)
    def test_f4_selection_monotonicity(
        self, dummy_diagram: Path, model_data: tuple[list[str], list[str], list[str]]
    ) -> None:
        """Excluded entities stay excluded: they never appear in new_entity_ids on refresh."""
        all_ids, _, excluded = model_data
        assume(len(all_ids) > 0)
        query = FakeQuery(entities=[_entity(eid) for eid in all_ids])
        vd = _make_vd(all_ids, selected=[], excluded=excluded)
        diff = compute_derivation_diff(dummy_diagram, {}, vd, query, _ES_CATALOG)
        overlap = set(diff.new_entity_ids) & set(excluded)
        assert not overlap, f"excluded ids appeared as new candidates: {overlap}"

    @given(_entity_model())
    @settings(max_examples=150, deadline=None)
    def test_f4_no_silent_mutation(
        self, dummy_diagram: Path, model_data: tuple[list[str], list[str], list[str]]
    ) -> None:
        """Neither F_θ nor Refresh writes to M: model entity/connection sets unchanged."""
        all_ids, selected, excluded = model_data
        query = FakeQuery(entities=[_entity(eid) for eid in all_ids])
        entities_before = frozenset(query.entity_ids())
        connections_before = frozenset(query.connection_ids())

        es_derive({"entity_ids": selected}, _SNAPSHOT, query)
        vd = _make_vd(all_ids, selected=selected, excluded=excluded)
        compute_derivation_diff(dummy_diagram, {}, vd, query, _ES_CATALOG)

        assert frozenset(query.entity_ids()) == entities_before
        assert frozenset(query.connection_ids()) == connections_before
