"""The frontend's timeout-policy document agrees with the route-policy manifest.

The manifest decides which operations are ``derived-graph`` or ``streaming``. Two frontend consumers
need that — the HTTP client and the Vite dev config — and they live in different TypeScript programs,
so no module can be shared between them. The document is therefore *generated* from the manifest and
committed, and neither consumer derives anything from it: even the dev-proxy context patterns and
their ordering arrive already computed, so two readings of one file cannot diverge.

What remains to check is drift between the committed copy and the manifest, plus the properties the
derivation is supposed to have. A stale copy is invisible in development until a request that needs
60 s is severed at 15 s and reported as ``ERR_EMPTY_RESPONSE``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.infrastructure.gui.route_policy import ROUTE_POLICY
from src.infrastructure.gui.route_policy.timeout_policy_document import (
    NON_DEFAULT_CLASSES,
    serialize,
    template_pattern,
)
from tools.openapi.generate_timeout_policy import DOCUMENT


@pytest.fixture(scope="module")
def committed() -> dict[str, Any]:
    return json.loads(DOCUMENT.read_text(encoding="utf-8"))


def test_the_committed_document_matches_the_manifest() -> None:
    """The drift gate, in the suite as well as in CI — a frontend built from a stale document
    would silently disagree with the backend about how long an operation may take."""
    assert DOCUMENT.read_text(encoding="utf-8") == serialize(ROUTE_POLICY), (
        "routeTimeoutPolicy.json is stale — run "
        "`uv run tools/openapi/generate_timeout_policy.py` and commit the result."
    )


@pytest.mark.parametrize("timeout_class", NON_DEFAULT_CLASSES)
def test_canonical_templates_are_the_manifests(
    timeout_class: str, committed: dict[str, Any]
) -> None:
    expected = sorted(row.template for row in ROUTE_POLICY if row.timeout_class == timeout_class)
    assert committed["templates"][timeout_class] == expected


@pytest.mark.parametrize("timeout_class", NON_DEFAULT_CLASSES)
def test_every_template_has_a_proxy_context(
    timeout_class: str, committed: dict[str, Any]
) -> None:
    templates = committed["templates"][timeout_class]
    assert sorted(committed["proxyContexts"][timeout_class]) == sorted(
        template_pattern(template) for template in templates
    )


def test_a_longer_template_is_offered_before_the_shorter_one_it_extends(
    committed: dict[str, Any],
) -> None:
    """Vite uses the first context that matches, so a specific rule listed after a broader one
    never fires."""
    contexts = committed["proxyContexts"]["derived-graph"]
    svg = contexts.index(template_pattern("/api/diagrams/{artifact_id}/svg"))
    detail = contexts.index(template_pattern("/api/diagrams/{artifact_id}"))
    assert svg < detail


def test_a_pattern_terminates_at_the_query_separator(committed: dict[str, Any]) -> None:
    """A dev proxy matches against the request URL, query string included; an end-anchored pattern
    would fail on every request that has one."""
    for timeout_class in NON_DEFAULT_CLASSES:
        for pattern in committed["proxyContexts"][timeout_class]:
            assert pattern.startswith("^")
            assert pattern.endswith(r"(\?|$)")


def test_the_client_aborts_before_the_proxy_does(committed: dict[str, Any]) -> None:
    """The client's own abort produces a typed timeout the UI can explain; a proxy that gives up
    first produces ``ERR_EMPTY_RESPONSE`` and looks like a crashed backend."""
    assert committed["proxyHeadroomMs"] > 0


def test_the_streaming_class_has_no_budget_at_all(committed: dict[str, Any]) -> None:
    """A budget on the event stream severs it and triggers a reconnect storm."""
    assert committed["budgetMs"]["streaming"] is None


def test_derived_graph_exceeds_the_generic_budget(committed: dict[str, Any]) -> None:
    assert committed["budgetMs"]["derived-graph"] > committed["budgetMs"]["default"]


def test_every_operation_declares_a_timeout_class() -> None:
    for row in ROUTE_POLICY:
        assert row.timeout_class in ("default", *NON_DEFAULT_CLASSES), row.operation_id


def test_only_the_event_stream_is_classified_streaming() -> None:
    streaming = {row.operation_id for row in ROUTE_POLICY if row.timeout_class == "streaming"}
    assert streaming == {"events_stream_events"}
