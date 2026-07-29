"""`slug` is a lexical refinement of `string`, not a separate value space.

Nothing enforces slug form at runtime (scalar binding accepts any ``str``), so the two must
compare and pattern-match interchangeably. Keeping them incompatible made slug-typed
parameters unusable against the reserved `group`/`specialization` paths, which resolve as
plain strings — the shipped motivation-coverage `group` filter is the regression case.
"""

from __future__ import annotations

import pytest

from src.domain.viewpoints.viewpoint_criteria import (
    STRING_ATTRIBUTE_TYPES,
    STRING_LIKE_ATTRIBUTE_TYPES,
    scalar_kinds_comparable,
)
from src.domain.viewpoints.viewpoint_value_types import (
    BindingTypeError,
    ScalarType,
    assert_types_are_compatible,
    types_are_compatible,
)


class TestLatticeRule:
    def test_slug_and_string_are_mutually_comparable(self) -> None:
        assert scalar_kinds_comparable("slug", "string")
        assert scalar_kinds_comparable("string", "slug")

    def test_identical_kinds_stay_comparable(self) -> None:
        for kind in ("string", "slug", "integer", "number", "date", "boolean"):
            assert scalar_kinds_comparable(kind, kind)

    @pytest.mark.parametrize("other", ["integer", "number", "date", "boolean"])
    def test_string_like_is_not_comparable_to_other_kinds(self, other: str) -> None:
        # The widening is deliberately narrow: only the string-like pair, never numerics.
        assert not scalar_kinds_comparable("string", other)
        assert not scalar_kinds_comparable("slug", other)

    def test_pattern_operators_accept_both_string_like_kinds(self) -> None:
        assert STRING_ATTRIBUTE_TYPES == STRING_LIKE_ATTRIBUTE_TYPES == frozenset({"string", "slug"})


class TestBindingCompatibility:
    def test_slug_binding_satisfies_a_string_declaration(self) -> None:
        assert types_are_compatible(ScalarType("string"), ScalarType("slug"))
        assert types_are_compatible(ScalarType("slug"), ScalarType("string"))

    def test_numeric_mismatch_still_raises(self) -> None:
        with pytest.raises(BindingTypeError):
            assert_types_are_compatible(ScalarType("string"), ScalarType("integer"))
