"""Unit tests for DerivationStrategyCatalogBuilder and DerivationStrategyCatalog."""

from __future__ import annotations

import pytest

from src.application.derivation.strategy_registry import (
    DerivationStrategyCatalog,
    DerivationStrategyCatalogBuilder,
)
from src.domain.relationships.derivation_types import StrategySpec

_SPEC_A = StrategySpec(name="scope-projection", version=1, supported_filters=frozenset({"domain"}))
_SPEC_B = StrategySpec(name="neighborhood", version=2, supported_filters=frozenset())


def _derive_fn_a(x: object) -> object:
    return x


# ── Builder lifecycle ─────────────────────────────────────────────────────────


class TestBuilderLifecycle:
    def test_build_returns_catalog(self) -> None:
        b = DerivationStrategyCatalogBuilder()
        cat = b.build()
        assert isinstance(cat, DerivationStrategyCatalog)

    def test_register_then_build(self) -> None:
        b = DerivationStrategyCatalogBuilder()
        b.register(_SPEC_A)
        cat = b.build()
        assert cat.lookup_strategy("scope-projection", 1) is _SPEC_A

    def test_register_with_fn(self) -> None:
        b = DerivationStrategyCatalogBuilder()
        b.register(_SPEC_A, _derive_fn_a)
        cat = b.build()
        assert cat.lookup_derive_fn("scope-projection", 1) is _derive_fn_a

    def test_register_after_build_raises(self) -> None:
        b = DerivationStrategyCatalogBuilder()
        b.build()
        with pytest.raises(RuntimeError, match="already been built"):
            b.register(_SPEC_A)

    def test_multiple_strategies(self) -> None:
        b = DerivationStrategyCatalogBuilder()
        b.register(_SPEC_A)
        b.register(_SPEC_B)
        cat = b.build()
        assert cat.lookup_strategy("scope-projection", 1) is _SPEC_A
        assert cat.lookup_strategy("neighborhood", 2) is _SPEC_B

    def test_replace_before_build(self) -> None:
        spec_v1 = StrategySpec("my-strat", version=1, supported_filters=frozenset())
        spec_v2 = StrategySpec("my-strat", version=1, supported_filters=frozenset({"tag"}))
        b = DerivationStrategyCatalogBuilder()
        b.register(spec_v1)
        b.register(spec_v2)  # same key replaces v1
        cat = b.build()
        result = cat.lookup_strategy("my-strat", 1)
        assert result is spec_v2


# ── Catalog queries ───────────────────────────────────────────────────────────


class TestCatalogQueries:
    def _build(self, *specs_and_fns: tuple | StrategySpec) -> DerivationStrategyCatalog:
        b = DerivationStrategyCatalogBuilder()
        for item in specs_and_fns:
            if isinstance(item, tuple):
                b.register(item[0], item[1])
            else:
                b.register(item)
        return b.build()

    def test_lookup_strategy_found(self) -> None:
        cat = self._build(_SPEC_A)
        assert cat.lookup_strategy("scope-projection", 1) is _SPEC_A

    def test_lookup_strategy_wrong_version(self) -> None:
        cat = self._build(_SPEC_A)
        assert cat.lookup_strategy("scope-projection", 99) is None

    def test_lookup_strategy_missing(self) -> None:
        cat = self._build()
        assert cat.lookup_strategy("no-such", 1) is None

    def test_lookup_derive_fn_present(self) -> None:
        cat = self._build((_SPEC_A, _derive_fn_a))
        assert cat.lookup_derive_fn("scope-projection", 1) is _derive_fn_a

    def test_lookup_derive_fn_absent(self) -> None:
        cat = self._build(_SPEC_A)  # no fn
        assert cat.lookup_derive_fn("scope-projection", 1) is None

    def test_registered_strategies_all_present(self) -> None:
        cat = self._build(_SPEC_A, _SPEC_B)
        specs = cat.registered_strategies()
        assert _SPEC_A in specs
        assert _SPEC_B in specs

    def test_registered_strategies_empty(self) -> None:
        cat = self._build()
        assert cat.registered_strategies() == []


# ── Independence between catalogs ────────────────────────────────────────────


class TestNoGlobalState:
    def test_two_catalogs_are_independent(self) -> None:
        b1 = DerivationStrategyCatalogBuilder()
        b1.register(_SPEC_A)
        cat1 = b1.build()

        b2 = DerivationStrategyCatalogBuilder()
        b2.register(_SPEC_B)
        cat2 = b2.build()

        assert cat1.lookup_strategy("scope-projection", 1) is _SPEC_A
        assert cat1.lookup_strategy("neighborhood", 2) is None
        assert cat2.lookup_strategy("neighborhood", 2) is _SPEC_B
        assert cat2.lookup_strategy("scope-projection", 1) is None
