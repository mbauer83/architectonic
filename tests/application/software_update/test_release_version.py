"""One reading of the release version, and an ordering that agrees with the numbers."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.application.software_update.version import NotAReleaseVersion, ReleaseVersion, parse_release_version

parts = st.integers(min_value=0, max_value=10_000)


@given(parts, parts, parts)
def test_the_spelling_reads_back_with_and_without_the_tag_prefix(major: int, minor: int, patch: int) -> None:
    version = ReleaseVersion(major, minor, patch)

    assert parse_release_version(str(version)) == version
    assert parse_release_version(version.tag) == version
    assert version.tag == f"v{major}.{minor}.{patch}"


@given(st.tuples(parts, parts, parts), st.tuples(parts, parts, parts))
def test_ordering_is_the_numeric_ordering_of_the_triple(a: tuple[int, int, int], b: tuple[int, int, int]) -> None:
    assert (ReleaseVersion(*a) < ReleaseVersion(*b)) == (a < b)
    assert (ReleaseVersion(*a) == ReleaseVersion(*b)) == (a == b)


def test_ten_orders_after_nine_numerically_rather_than_lexically() -> None:
    assert parse_release_version("0.9.0") < parse_release_version("0.10.0")
    assert max([parse_release_version(v) for v in ("0.9.0", "0.10.0", "0.9.1")]) == ReleaseVersion(0, 10, 0)


@pytest.mark.parametrize("text", ["0.10", "0.10.0-rc1", "v", "0.10.0.1", "abc", "", "0.10.0+build"])
def test_anything_but_the_three_part_form_is_refused_by_name(text: str) -> None:
    with pytest.raises(NotAReleaseVersion):
        parse_release_version(text)
