"""Composition/aggregation parity (ArchiMate 4 spec §5.1.2): a composition relationship is
allowed in exactly the same cases where an aggregation relationship would be allowed."""

from __future__ import annotations

from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.ontologies.archimate_4._loader import _PACKAGE_DIR, load_archimate_4_module

# technology-node -> artifact is a pre-existing aggregation rule that Appendix B's Technology
# domain table does not support in either direction (no "G" cell for that pair or its
# reverse); flagged for the WU-C2 systematic Appendix B recheck rather than fixed here, so it
# is the one documented exception to the composition-mirrors-aggregation invariant below.
_KNOWN_AGGREGATION_ONLY_EXCEPTIONS = frozenset({("technology-node", "artifact")})


def test_composition_permitted_wherever_aggregation_is() -> None:
    module = load_archimate_4_module(_PACKAGE_DIR)
    rules = module.permitted_relationships

    aggregation_pairs = set()
    composition_pairs = set()
    for src, entries in rules.by_source().items():
        for tgt, conn in entries:
            if conn == "archimate-aggregation":
                aggregation_pairs.add((str(src), str(tgt)))
            elif conn == "archimate-composition":
                composition_pairs.add((str(src), str(tgt)))

    missing_composition = aggregation_pairs - composition_pairs - _KNOWN_AGGREGATION_ONLY_EXCEPTIONS
    assert missing_composition == set(), (
        f"composition must be permitted wherever aggregation is (spec §5.1.2): {sorted(missing_composition)}"
    )


def test_known_exception_is_still_aggregation_only() -> None:
    """Guards the documented exception itself: if a future spec-aligned fix adds composition
    here, this test should start failing so the exception set gets deliberately trimmed."""
    module = load_archimate_4_module(_PACKAGE_DIR)
    rules = module.permitted_relationships

    for source, target in _KNOWN_AGGREGATION_ONLY_EXCEPTIONS:
        src, tgt = EntityTypeName(source), EntityTypeName(target)
        assert rules.permits(src, tgt, ConnectionTypeName("archimate-aggregation"))
        assert not rules.permits(src, tgt, ConnectionTypeName("archimate-composition"))
