"""OSV two-phase client over an injected httpx MockTransport (no network):
querybatch index mapping + per-query pagination, detail fan-out dedup,
bounded retries with eventual partial-source reporting, and 4xx non-retry."""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx

from src.infrastructure.assurance.osv_client import OsvClient, OsvComponentQuery

Q_A = OsvComponentQuery(component_id="C-a", purl="pkg:pypi/a@1.0.0")
Q_B = OsvComponentQuery(component_id="C-b", purl="pkg:pypi/b@2.0.0")


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> OsvClient:
    transport = httpx.MockTransport(handler)
    return OsvClient(httpx.Client(transport=transport), sleep=lambda _s: None)


class TestQuerybatch:
    def test_results_map_back_by_index_and_details_dedup(self) -> None:
        detail_calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v1/querybatch":
                return httpx.Response(200, json={"results": [
                    {"vulns": [{"id": "OSV-1"}, {"id": "OSV-2"}]},
                    {"vulns": [{"id": "OSV-1"}]},  # shared with component a
                ]})
            detail_calls.append(request.url.path)
            vuln_id = request.url.path.rsplit("/", 1)[1]
            return httpx.Response(200, json={"id": vuln_id, "summary": "x"})

        acq = _client(handler).query_components([Q_A, Q_B])
        assert acq.vulnerability_ids_by_component == {
            "C-a": ["OSV-1", "OSV-2"], "C-b": ["OSV-1"],
        }
        assert sorted(acq.vulnerabilities_by_id) == ["OSV-1", "OSV-2"]
        assert sorted(detail_calls) == ["/v1/vulns/OSV-1", "/v1/vulns/OSV-2"]  # deduped

    def test_per_query_pagination_follows_next_page_token(self) -> None:
        batch_bodies: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v1/querybatch":
                body = json.loads(request.content)
                batch_bodies.append(body)
                if len(batch_bodies) == 1:
                    return httpx.Response(200, json={"results": [
                        {"vulns": [{"id": "OSV-1"}], "next_page_token": "t1"},
                        {"vulns": [{"id": "OSV-9"}]},
                    ]})
                return httpx.Response(200, json={"results": [
                    {"vulns": [{"id": "OSV-2"}]},
                ]})
            return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[1]})

        acq = _client(handler).query_components([Q_A, Q_B])
        assert acq.vulnerability_ids_by_component["C-a"] == ["OSV-1", "OSV-2"]
        assert acq.vulnerability_ids_by_component["C-b"] == ["OSV-9"]
        # The second round only re-queried the paginated component, with its token.
        assert len(batch_bodies[1]["queries"]) == 1
        assert batch_bodies[1]["queries"][0]["page_token"] == "t1"


class TestFailureModes:
    def test_5xx_retries_then_reports_partial_source(self) -> None:
        attempts = {"batch": 0, "detail": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v1/querybatch":
                attempts["batch"] += 1
                return httpx.Response(200, json={"results": [
                    {"vulns": [{"id": "OSV-1"}]},
                ]})
            attempts["detail"] += 1
            return httpx.Response(503)

        acq = _client(handler).query_components([Q_A])
        assert attempts["detail"] == 3  # bounded retries
        assert acq.vulnerabilities_by_id == {}
        assert acq.failed_vulnerability_fetches == [{
            "vulnerability_id": "OSV-1", "reason": "detail fetch failed after retries",
        }]

    def test_batch_failure_marks_components_unmatched_not_silent(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        acq = _client(handler).query_components([Q_A, Q_B])
        assert {u["component_id"] for u in acq.unmatched_components} == {"C-a", "C-b"}
        assert acq.queried_component_count == 2

    def test_4xx_is_not_retried(self) -> None:
        attempts = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["n"] += 1
            return httpx.Response(400)

        _client(handler).query_components([Q_A])
        assert attempts["n"] == 1
