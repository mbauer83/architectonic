from pathlib import Path

from src.infrastructure.mcp.artifact_mcp import context


def test_backend_environment_configures_mcp_repo_roots(monkeypatch) -> None:
    monkeypatch.setenv("ARCH_REPO_ROOT", "/deployment/engagement")
    monkeypatch.setenv("ARCH_ENTERPRISE_ROOT", "/deployment/enterprise")
    monkeypatch.delenv("ARCH_MCP_MODEL_REPO_ROOT", raising=False)

    assert context.default_engagement_repo_root() == Path("/deployment/engagement")
    assert context.default_enterprise_repo_root() == Path("/deployment/enterprise")


def test_mcp_specific_engagement_override_has_precedence(monkeypatch) -> None:
    monkeypatch.setenv("ARCH_REPO_ROOT", "/backend/engagement")
    monkeypatch.setenv("ARCH_MCP_MODEL_REPO_ROOT", "/mcp/engagement")

    assert context.default_engagement_repo_root() == Path("/mcp/engagement")
