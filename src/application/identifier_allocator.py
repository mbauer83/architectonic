"""System-wide identifier allocator for canonical artifact IDs.

Provides a protocol and a default implementation that wraps the canonical
TYPE@epoch.random.slug mint algorithm. All artifact-id creation — model entities,
diagrams, documents, GARs, and workspace-identified diagram entities (classifiers)
— should delegate to this allocator.

The allocator itself is stateless; it mints IDs but does not reserve them. Final
candidate verification enforces uniqueness.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.application.modeling.artifact_write import generate_entity_id


@runtime_checkable
class IdentifierAllocator(Protocol):
    """Canonical source of artifact IDs for the workspace.

    The caller is responsible for resolving ``prefix`` from the entity-type's
    ``id_prefix`` metadata (WU-0.1). Arbitrary or invented prefixes must not be
    passed by callers.
    """

    def allocate(self, *, prefix: str, name_hint: str | None) -> str:
        """Mint a new ``TYPE@epoch.random.slug`` id.

        Args:
            prefix: The type prefix (e.g. ``CLF``, ``APP``), resolved from
                ``id_prefix`` metadata — not caller-invented.
            name_hint: Optional human-readable name used to derive the slug.
        """
        ...


class DefaultIdentifierAllocator:
    """Default allocator wrapping the canonical generate_entity_id algorithm."""

    def allocate(self, *, prefix: str, name_hint: str | None) -> str:
        return generate_entity_id(prefix, name_hint or "entity")


_default_allocator = DefaultIdentifierAllocator()


def get_default_allocator() -> IdentifierAllocator:
    return _default_allocator
