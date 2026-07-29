"""The `count | sum | avg | min | max` reduction shared by every derived-attribute
evaluator — pulled out on its own so the direct-traversal and batched relationship-derived
evaluators can both use it without either importing the other."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from src.domain.ontology_representation.attribute_scales import ordinal_extreme


def reduce_values(value: object, reduce: str, *, ordinal_scale: Sequence[str] | None = None) -> object:
    """Reduce derived values, ranking by an ordinal scale where one is supplied.

    Without a scale, `min`/`max` fall back to the values' natural ordering, which is correct for
    numbers and dates and alphabetical for strings. An ordinal's members are not alphabetical,
    so ranking them needs the scale — passing it is what makes `max` over a severity mean the
    worst one rather than the last one in the dictionary.
    """
    values = value if isinstance(value, tuple) else (value,)
    present = tuple(item for item in values if item is not None)
    if reduce == "count":
        return len(present)
    if ordinal_scale is not None and reduce in ("min", "max"):
        return ordinal_extreme(present, highest=reduce == "max", scale=ordinal_scale)
    if reduce == "sum":
        return sum(cast(tuple[int | float, ...], present)) if present else 0
    if reduce == "avg":
        return sum(cast(tuple[int | float, ...], present)) / len(present) if present else None
    if reduce == "min":
        return min(cast(tuple[str | int | float, ...], present)) if present else None
    if reduce == "max":
        return max(cast(tuple[str | int | float, ...], present)) if present else None
    raise AssertionError(f"unhandled reduction {reduce!r}")
