"""The section views partition the served surface: nothing lost, nothing shown twice.

`/docs/architecture` and `/docs/assurance` are filters over the one document, which is the answer to
"can the OpenAPI be partitioned safely and consistently" — it can, as *views*, because a filter cannot
go stale against the thing it filters. What a filter *can* do is silently drop an operation, and that is
what these hold.

The property is the whole point. Split into separate documents, the equivalent guarantee would need
schema-ownership rules for 391 components and a check that no `$ref` crosses a boundary. Here it is one
subtraction: `architecture` is every tag that is not an assurance tag, so an operation reaches exactly
one view by construction and a new section joins `architecture` without anyone editing a list.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.infrastructure.rest.routers._docs_views import (
    SECTION_TAGS,
    filtered_document,
)


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    from src.infrastructure.backend.arch_backend_app import _build_app

    return _build_app().openapi()


def _operation_ids(document: dict[str, Any]) -> set[str]:
    return {
        operation["operationId"]
        for methods in document.get("paths", {}).values()
        for operation in methods.values()
        if isinstance(operation, dict) and operation.get("operationId")
    }


def test_the_views_together_cover_every_operation(document: dict[str, Any]) -> None:
    """A reader who opens both views has seen the whole surface."""
    everything = _operation_ids(document)
    assert len(everything) > 100, len(everything)

    covered: set[str] = set()
    for tags in SECTION_TAGS.values():
        covered |= _operation_ids(filtered_document(document, tags))

    missing = sorted(everything - covered)
    assert missing == [], (
        f"{len(missing)} operations appear in no section view, so they are reachable only from the "
        f"unfiltered /docs: {missing}"
    )


def test_no_operation_appears_in_two_views(document: dict[str, Any]) -> None:
    """Disjointness, which is what makes "how big is this section" answerable by counting."""
    seen: dict[str, str] = {}
    duplicated: list[tuple[str, str, str]] = []
    for section, tags in SECTION_TAGS.items():
        for operation in _operation_ids(filtered_document(document, tags)):
            if operation in seen:
                duplicated.append((operation, seen[operation], section))
            seen[operation] = section
    assert duplicated == [], duplicated


def test_filtering_does_not_consume_the_document(document: dict[str, Any]) -> None:
    """The deep copy, asserted.

    FastAPI caches `app.openapi()` and returns the same object every time. Filtering it in place would
    make the first section view requested the only document the process served again — `/openapi.json`
    would answer with whatever subset happened to be asked for first, and only under load, in a
    long-running process, in an order no test controls.
    """
    before = _operation_ids(document)
    for tags in SECTION_TAGS.values():
        filtered_document(document, tags)
    assert _operation_ids(document) == before


def test_a_view_keeps_its_paths_whole(document: dict[str, Any]) -> None:
    """A path kept for one operation does not smuggle its siblings in.

    `/api/assurance/analyses/{analysis_id}` carries GET, PATCH and DELETE. Filtering by path rather
    than by operation would have pulled every method along with the first match, which is invisible
    while a path's methods happen to share a tag.
    """
    assurance = filtered_document(document, SECTION_TAGS["assurance"])
    for path, methods in assurance["paths"].items():
        for method, operation in methods.items():
            if isinstance(operation, dict) and operation.get("operationId"):
                tags = set(operation.get("tags") or ())
                assert tags & SECTION_TAGS["assurance"], (path, method, sorted(tags))


def test_each_view_declares_only_its_own_tags(document: dict[str, Any]) -> None:
    """The tag list travels with the view, so Swagger UI shows no empty headings."""
    for section, tags in SECTION_TAGS.items():
        view = filtered_document(document, tags)
        declared = {entry["name"] for entry in view.get("tags", [])}
        assert declared <= tags, (section, sorted(declared - tags))
