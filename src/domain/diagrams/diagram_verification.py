"""Per-diagram and per-transaction verification contribution protocols.

WU-0.7: DiagramVerificationContribution — runs once per diagram file.
WU-0.7b: RepositoryVerificationContribution — runs once per candidate transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class BaseDiagramVerificationContext:
    """Context provided to per-diagram contributions."""

    fm: dict
    loc: str
    scope: Literal["enterprise", "engagement", "unknown"]
    diagram_id: str
    allowed_connections: frozenset[str]
    allowed_entities: frozenset[str]
    catalogs: Any
    type_references_blocking: bool = True


class DiagramVerificationContribution(Protocol):
    diagnostic_codes: tuple[str, ...]

    def run(self, candidate: Any, ctx: BaseDiagramVerificationContext, result: Any) -> None: ...


@dataclass(frozen=True)
class RepositoryVerificationContext:
    """Context provided to per-transaction repository contributions."""

    committed: Any
    candidate: Any
    location: str
    catalogs: Any = None
    type_references_blocking: bool = True


class RepositoryVerificationContribution(Protocol):
    diagnostic_codes: tuple[str, ...]

    def run(self, ctx: RepositoryVerificationContext, result: Any) -> None: ...


# Central registry for generic (non-module) repository contributions.
# WU-0.6 will append the E335 workspace-id-uniqueness contribution here.
_GENERIC_REPOSITORY_CONTRIBUTIONS: list[RepositoryVerificationContribution] = []


def get_generic_repository_contributions() -> tuple[RepositoryVerificationContribution, ...]:
    """Return the current set of generic repository contributions."""
    return tuple(_GENERIC_REPOSITORY_CONTRIBUTIONS)
