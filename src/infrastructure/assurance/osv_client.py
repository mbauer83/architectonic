"""Two-phase OSV.dev client (§6.0(g)).

Phase 1: ``POST /v1/querybatch`` with valid versioned package identities —
one query per component, paginated per query via ``next_page_token``; results
map back to components by index. Malformed or versionless components never
reach the API: they land in explicit ``unmatched`` diagnostics.

Phase 2: ``GET /v1/vulns/{id}`` fan-out, deduplicated across components,
bounded retries with backoff, per-request timeout. A vulnerability that still
fails after retries is recorded in ``failed_vulnerability_fetches`` and the
acquisition continues — partial-source reporting, never a silent gap.

The transport is injectable (httpx client) so every failure path is testable
without network; CI runs no network calls.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import httpx

logger = logging.getLogger(__name__)

OSV_BASE_URL = "https://api.osv.dev"
_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 0.5
_TIMEOUT_SECONDS = 20.0
_QUERYBATCH_CHUNK = 100


@dataclass(frozen=True)
class OsvComponentQuery:
    component_id: str
    purl: str  # versioned purl, validated by the caller


@dataclass
class OsvAcquisition:
    """Everything phase 1+2 learned, plus honest diagnostics."""

    vulnerability_ids_by_component: dict[str, list[str]] = field(default_factory=dict)
    vulnerabilities_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    unmatched_components: list[dict[str, str]] = field(default_factory=list)
    failed_vulnerability_fetches: list[dict[str, str]] = field(default_factory=list)
    queried_component_count: int = 0


class OsvClient:
    def __init__(
        self,
        http: httpx.Client | None = None,
        *,
        base_url: str = OSV_BASE_URL,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = http or httpx.Client(timeout=_TIMEOUT_SECONDS)
        self._base_url = base_url.rstrip("/")
        self._sleep = sleep

    # ── Phase 1 ───────────────────────────────────────────────────────────────

    def query_components(self, queries: Sequence[OsvComponentQuery]) -> OsvAcquisition:
        acquisition = OsvAcquisition(queried_component_count=len(queries))
        for start in range(0, len(queries), _QUERYBATCH_CHUNK):
            chunk = list(queries[start:start + _QUERYBATCH_CHUNK])
            self._querybatch_chunk(chunk, acquisition)
        self._fetch_details(acquisition)
        return acquisition

    def _querybatch_chunk(
        self, chunk: list[OsvComponentQuery], acquisition: OsvAcquisition,
    ) -> None:
        pending: list[tuple[OsvComponentQuery, str]] = [(q, "") for q in chunk]
        while pending:
            body = {
                "queries": [
                    {"package": {"purl": query.purl}, **({"page_token": token} if token else {})}
                    for query, token in pending
                ]
            }
            response = self._request_with_retries(
                "POST", f"{self._base_url}/v1/querybatch", json=body,
            )
            if response is None:
                for query, _token in pending:
                    acquisition.unmatched_components.append({
                        "component_id": query.component_id,
                        "reason": "querybatch request failed after retries",
                    })
                return
            results = response.get("results", [])
            next_round: list[tuple[OsvComponentQuery, str]] = []
            for (query, _token), result in zip(pending, results):
                vulns: list[dict[str, Any]] = result.get("vulns") or []
                ids = acquisition.vulnerability_ids_by_component.setdefault(
                    query.component_id, [])
                for vuln in vulns:
                    vuln_id = str(vuln.get("id", ""))
                    if vuln_id and vuln_id not in ids:
                        ids.append(vuln_id)
                token = str(result.get("next_page_token") or "")
                if token:
                    next_round.append((query, token))
            pending = next_round

    # ── Phase 2 ───────────────────────────────────────────────────────────────

    def _fetch_details(self, acquisition: OsvAcquisition) -> None:
        unique_ids = sorted({
            vuln_id
            for ids in acquisition.vulnerability_ids_by_component.values()
            for vuln_id in ids
        })
        for vuln_id in unique_ids:
            detail = self._request_with_retries(
                "GET", f"{self._base_url}/v1/vulns/{vuln_id}",
            )
            if detail is None:
                acquisition.failed_vulnerability_fetches.append({
                    "vulnerability_id": vuln_id,
                    "reason": "detail fetch failed after retries",
                })
                continue
            acquisition.vulnerabilities_by_id[vuln_id] = detail

    # ── Transport ─────────────────────────────────────────────────────────────

    def _request_with_retries(
        self, method: str, url: str, *, json: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        for attempt in range(_MAX_RETRIES):
            try:
                response = self._http.request(method, url, json=json)
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"server error {response.status_code}",
                        request=response.request, response=response,
                    )
                if response.status_code >= 400:
                    logger.warning("OSV %s %s → %d (not retried)", method, url, response.status_code)
                    return None
                payload = response.json()
                return payload if isinstance(payload, dict) else None
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("OSV %s %s attempt %d failed: %s", method, url, attempt + 1, exc)
                if attempt + 1 < _MAX_RETRIES:
                    self._sleep(_RETRY_BACKOFF_SECONDS * (2 ** attempt))
        return None
