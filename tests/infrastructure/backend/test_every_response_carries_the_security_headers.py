"""Every response tells the browser what the page may do.

Regression: no response carried a content security policy, `nosniff`, a framing refusal or a referrer
policy, so a sanitiser missed in one of the GUI's HTML sinks would have run whatever it let through,
and any site could frame the GUI.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.backend.arch_backend_app import _build_app
from src.infrastructure.backend.security_headers import APPLICATION_POLICY, DOCUMENTATION_POLICY


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app(), base_url="http://localhost:8000")


@pytest.mark.parametrize("path", ["/health", "/api/modules", "/", "/entities/anything", "/api/no-such-route"])
def test_the_application_policy_is_on_every_response(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.headers["content-security-policy"] == APPLICATION_POLICY
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "same-origin"
    assert response.headers["x-frame-options"] == "DENY"


def test_the_policy_admits_no_inline_or_foreign_script_and_no_framing() -> None:
    directives = dict(
        (part.split(" ", 1)[0], part.split(" ", 1)[1]) for part in APPLICATION_POLICY.split("; ")
    )

    assert directives["default-src"] == "'self'"
    assert directives["script-src"] == "'self'"
    assert directives["frame-ancestors"] == "'none'"
    assert directives["object-src"] == "'none'"


def test_a_refused_host_still_gets_the_headers() -> None:
    response = TestClient(_build_app(), base_url="http://attacker.example").get("/")

    assert response.status_code == 421
    assert response.headers["content-security-policy"] == APPLICATION_POLICY


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/docs/architecture"])
def test_the_documentation_pages_get_their_own_policy(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-security-policy"] == DOCUMENTATION_POLICY

