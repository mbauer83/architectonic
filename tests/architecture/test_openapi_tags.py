"""Every served operation carries exactly one tag, from a declared vocabulary.

A tag is the only thing that makes a 166-operation document navigable, and it was optional: **59
operations had none**, so `/docs` filed a third of the surface — the whole assurance module, plus sync,
promotion and the event stream — under an unnamed "default" heading. Nobody had forgotten on purpose;
the tag is a decorator keyword, and nothing compared the served surface against a vocabulary, so the
omission was invisible from inside the code and only visible to someone reading `/docs`.

Which is where it was found. That is the same shape as `NEVER_REQUESTED_OPERATIONS`: a property of the
*served* surface that no unit test looks at, needing a check that reads what the application actually
publishes rather than what any module intends.

**Exactly one, not at least one.** Two tags put an operation under two headings, and a reader who found
it under the first cannot tell whether the second holds more of the same kind. It also makes "how large
is this section" unanswerable by counting, which is the question that produced the assurance
subdivision.

**A closed vocabulary, not free strings.** FastAPI is happy to mint a heading from any string, so a typo
would present as a section of one — the failure looking exactly like the feature.
"""

from __future__ import annotations

import collections

import pytest

from src.infrastructure.rest.routers._openapi import ALL_TAGS


@pytest.fixture(scope="module")
def operations() -> list[tuple[str, str, list[str]]]:
    """(operation_id, "METHOD /path", tags) for every operation the application publishes.

    Built from the app's own schema rather than from the routers, because what a router declares and
    what the composed application serves are different questions — `include_router` merges tags, and a
    router mounted twice would publish twice.
    """
    from src.infrastructure.backend.arch_backend_app import _build_app

    document = _build_app().openapi()
    found: list[tuple[str, str, list[str]]] = []
    for path, methods in document["paths"].items():
        for method, operation in methods.items():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            found.append(
                (operation["operationId"], f"{method.upper()} {path}", operation.get("tags") or [])
            )
    return found


def test_the_surface_is_worth_checking(operations: list[tuple[str, str, list[str]]]) -> None:
    """The precondition: an empty document would make every assertion below vacuously true."""
    assert len(operations) > 100, len(operations)


def test_every_operation_carries_exactly_one_tag(
    operations: list[tuple[str, str, list[str]]]
) -> None:
    untagged = sorted(where for _op, where, tags in operations if not tags)
    assert untagged == [], (
        f"{len(untagged)} operations publish no tag, so /docs files them under 'default': {untagged}"
    )

    multiple = sorted(
        (where, sorted(tags)) for _op, where, tags in operations if len(tags) > 1
    )
    assert multiple == [], f"operations under more than one heading: {multiple}"


def test_every_tag_is_declared(operations: list[tuple[str, str, list[str]]]) -> None:
    """A tag that is not in `ALL_TAGS` is a typo or a section nobody decided to add."""
    used = {tag for _op, _where, tags in operations for tag in tags}
    undeclared = sorted(used - ALL_TAGS)
    assert undeclared == [], (
        f"tags used but not declared in `_openapi.ALL_TAGS`: {undeclared}. "
        "Add the constant deliberately, or fix the spelling."
    )


def test_no_declared_tag_is_unused(operations: list[tuple[str, str, list[str]]]) -> None:
    """The other direction, so the vocabulary describes the surface rather than an intention.

    A declared-but-unused tag is a heading a reader never sees and a section a maintainer thinks
    exists — the same drift a shrink-only register prevents, in the documentation.
    """
    used = {tag for _op, _where, tags in operations for tag in tags}
    unused = sorted(ALL_TAGS - used)
    assert unused == [], f"declared tags no operation uses: {unused}"


def test_no_section_is_large_enough_to_be_unusable(
    operations: list[tuple[str, str, list[str]]]
) -> None:
    """A bound on section size, which is why the assurance surface is subdivided at all.

    One `assurance` tag held 62 operations once every route was tagged — twice the next largest, and a
    heading a reader collapses instead of using. The limit is generous and deliberately not tight: it
    catches a section that has become a dumping ground, not one that grew by three.

    `diagrams` at 31 is the largest legitimate section today. If a section passes 45 the answer is
    almost certainly to subdivide it along the sub-routers it already composes, as the assurance
    surface's six sections were.
    """
    sizes = collections.Counter(tag for _op, _where, tags in operations for tag in tags)
    oversized = {tag: n for tag, n in sizes.items() if n > 45}
    assert oversized == {}, (
        f"sections large enough that a reader cannot scan them: {oversized}. "
        "Subdivide along the routers the module already composes."
    )
