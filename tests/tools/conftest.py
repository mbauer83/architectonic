"""Shared test fixtures and session-scoped cleanup for tools tests."""

import os

import pytest

# Disable PlantUML syntax checking during tests to avoid JVM resource contention
# when many tests run concurrently.  The syntax check is an integration concern
# verified separately; unit/behavioural tests only care about file content and
# registry consistency.
os.environ.setdefault("ARCH_SKIP_PUML_SYNTAX", "1")


@pytest.fixture(autouse=True)
def clear_mcp_context_caches():
    """Clear all MCP context caches between tests to prevent cross-test pollution.

    The registry and repo LRU caches are keyed on repo root paths.  Tests that
    provide an isolated tmp_path repo can otherwise share cache entries with
    tests that previously loaded the real workspace repos from init-state.
    The init-state module-level flag must also be reset so the real workspace
    enterprise repo isn't silently loaded into subsequent isolated-repo tests.
    """
    import src.infrastructure.mcp.artifact_mcp.context as ctx
    from src.infrastructure.mcp.artifact_mcp.write_queue import shutdown as shutdown_write_queue

    shutdown_write_queue(wait=True)
    ctx.repo_cached.cache_clear()
    ctx.registry_cached.cache_clear()
    ctx._init_state = None
    ctx._init_state_loaded = False
    yield
    shutdown_write_queue(wait=True)
    ctx.repo_cached.cache_clear()
    ctx.registry_cached.cache_clear()
    ctx._init_state = None
    ctx._init_state_loaded = False
