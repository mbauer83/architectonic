"""Reusable identity-resolution assertions, applied to each canonical detail route as it lands.

The outcomes are decided once, in ADR *Resource Addressing*, and every path-addressed resource owes
the same answers. Writing them per router would mean re-deciding them per router, which is how a
surface ends up resolving ``%2F`` one way for entities and another for diagrams.

**Assert the outcome, never the mechanism.** Starlette resolves by declaration order; a test that
asserted the ordering would break on any upgrade that preserved the behaviour, and would pass on one
that changed the behaviour while keeping the ordering.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient


@dataclass(frozen=True)
class DetailRoute:
    """One path-addressed resource, and an identifier that genuinely resolves on it."""

    #: Concrete URL of a resource that exists, e.g. ``/api/entities/APP@1712870400.ab.thing``.
    resolving_url: str
    #: The same route with the identifier replaced by one that is well-formed but absent.
    unknown_url: str
    #: The same route with the identifier replaced by one outside the identifier grammar.
    malformed_url: str
    #: The collection the detail route hangs off, e.g. ``/api/entities``.
    collection_url: str


def assert_detail_route_resolves(client: TestClient, route: DetailRoute) -> None:
    """A well-formed, present identifier resolves."""
    assert client.get(route.resolving_url).status_code == 200, route.resolving_url


def assert_unknown_and_malformed_are_indistinguishable(
    client: TestClient, route: DetailRoute
) -> None:
    """Unknown, hidden and malformed identifiers all answer 404, uniformly.

    Distinguishing them would disclose existence: on the assurance surface, a 400 for a malformed id
    against a 404 for an absent one tells a reader which of two ids is *shaped* like a real one, and
    a 403 for a hidden one tells them it exists.
    """
    for url in (route.unknown_url, route.malformed_url):
        assert client.get(url).status_code == 404, url


def assert_incomplete_detail_path_is_not_the_collection(
    client: TestClient, route: DetailRoute
) -> None:
    """A detail path with the identifier omitted is 404, not a redirect to the collection."""
    response = client.get(f"{route.collection_url}/", follow_redirects=False)
    assert response.status_code == 404, response.status_code


def assert_collection_path_resolves_as_the_collection(
    client: TestClient, route: DetailRoute
) -> None:
    assert client.get(route.collection_url).status_code == 200, route.collection_url


def assert_conforms(client: TestClient, route: DetailRoute) -> None:
    """Every identity-resolution rule, for one route."""
    assert_detail_route_resolves(client, route)
    assert_unknown_and_malformed_are_indistinguishable(client, route)
    assert_incomplete_detail_path_is_not_the_collection(client, route)
    assert_collection_path_resolves_as_the_collection(client, route)
