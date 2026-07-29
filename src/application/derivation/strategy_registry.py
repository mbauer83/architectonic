"""Immutable derivation strategy catalog and its builder.

Strategy registration is performed exclusively at the composition root
(app_bootstrap.py). Consumers receive an injected DerivationStrategyCatalog.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.relationships.derivation_types import StrategySpec as StrategySpec  # re-export

if TYPE_CHECKING:
    from src.application.derivation.types import DeriveFn


class DerivationStrategyCatalog:
    """Immutable snapshot of registered derivation strategies.

    Produced by ``DerivationStrategyCatalogBuilder.build()``.
    """

    def __init__(
        self,
        specs: dict[tuple[str, int], StrategySpec],
        fns: dict[tuple[str, int], "DeriveFn"],
    ) -> None:
        self._specs = specs
        self._fns = fns

    def lookup_strategy(self, name: str, version: int) -> StrategySpec | None:
        return self._specs.get((name, version))

    def lookup_derive_fn(self, name: str, version: int) -> "DeriveFn | None":
        return self._fns.get((name, version))

    def registered_strategies(self) -> list[StrategySpec]:
        return list(self._specs.values())


class DerivationStrategyCatalogBuilder:
    """Mutable builder for derivation strategies; ``.build()`` seals it."""

    def __init__(self) -> None:
        self._specs: dict[tuple[str, int], StrategySpec] = {}
        self._fns: dict[tuple[str, int], "DeriveFn"] = {}
        self._built = False

    def _check_not_built(self) -> None:
        if self._built:
            raise RuntimeError("DerivationStrategyCatalogBuilder has already been built")

    def register(self, spec: StrategySpec, derive_fn: "DeriveFn | None" = None) -> None:
        self._check_not_built()
        self._specs[(spec.name, spec.version)] = spec
        if derive_fn is not None:
            self._fns[(spec.name, spec.version)] = derive_fn

    def build(self) -> DerivationStrategyCatalog:
        self._built = True
        return DerivationStrategyCatalog(dict(self._specs), dict(self._fns))
