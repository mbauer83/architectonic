"""Registry ⇔ manifest equality for the MCP write server.

Every tool on the write server is either a manifested mutator (carrying the
executor wrapper installed by ``register_mutation_tool``) or an explicitly
classified non-mutating tool; both directions of the equality hold, and every
manifest row's request builder is invoked against representative arguments.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from src.application.mutation_authorization import (
    DiscardWrite,
    MutationRequest,
    PromotionWrite,
    RepositoryWrite,
)
from src.infrastructure.mcp import mcp_artifact_server as srv
from src.infrastructure.mcp.artifact_mcp.mutation_registration import (
    MUTATION_TOOL_MANIFEST,
    NON_MUTATING_WRITE_TOOLS,
)


def _registered_write_tools() -> dict[str, object]:
    return dict(srv.mcp_write._tool_manager._tools)


class TestRegistryManifestEquality:
    def test_every_write_tool_is_classified_and_every_row_registered(self) -> None:
        registered = set(_registered_write_tools())
        classified = set(MUTATION_TOOL_MANIFEST) | NON_MUTATING_WRITE_TOOLS
        assert registered == classified

    def test_manifest_and_non_mutating_sets_are_disjoint(self) -> None:
        assert not set(MUTATION_TOOL_MANIFEST) & NON_MUTATING_WRITE_TOOLS

    def test_every_mutator_carries_the_executor_wrapper(self) -> None:
        for name in MUTATION_TOOL_MANIFEST:
            fn = _registered_write_tools()[name].fn  # type: ignore[attr-defined]
            assert getattr(fn, "__mutation_manifest_name__", None) == name, name
            assert inspect.iscoroutinefunction(fn), name
            assert hasattr(fn, "__wrapped__"), name

    def test_wrapper_preserves_tool_signature(self) -> None:
        """FastMCP derives schemas from the wrapper signature: it must equal the body's."""
        for name in MUTATION_TOOL_MANIFEST:
            fn = _registered_write_tools()[name].fn  # type: ignore[attr-defined]
            assert inspect.signature(fn) == inspect.signature(fn.__wrapped__), name

    def test_non_mutating_tools_carry_no_executor_wrapper(self) -> None:
        for name in NON_MUTATING_WRITE_TOOLS:
            fn = _registered_write_tools()[name].fn  # type: ignore[attr-defined]
            assert getattr(fn, "__mutation_manifest_name__", None) is None, name


class TestEveryRequestBuilderInvoked:
    @pytest.fixture()
    def roots(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
        engagement = tmp_path / "engagements" / "ENG-MAN" / "architecture-repository"
        enterprise = tmp_path / "enterprise-repository"
        engagement.mkdir(parents=True)
        enterprise.mkdir(parents=True)
        monkeypatch.setattr(
            "src.infrastructure.gui.routers.state.maybe_engagement_root", lambda: engagement
        )
        monkeypatch.setattr(
            "src.infrastructure.gui.routers.state.maybe_enterprise_root", lambda: enterprise
        )
        return engagement, enterprise

    def _representative_arguments(self, name: str, roots: tuple[Path, Path]) -> dict[str, object]:
        engagement, enterprise = roots
        match name:
            case "artifact_promote_to_enterprise":
                return {"repo_root": str(engagement), "enterprise_root": str(enterprise)}
            case "artifact_save_changes":
                return {"target": "engagement"}
            case "artifact_submit_for_review" | "artifact_withdraw_changes":
                return {}
            case _:
                return {"repo_root": str(engagement)}

    def test_each_builder_returns_a_declared_intent_and_typed_target(self, roots) -> None:
        engagement, enterprise = roots
        for name, row in MUTATION_TOOL_MANIFEST.items():
            request = row.build_request(self._representative_arguments(name, roots))
            assert isinstance(request, MutationRequest), name
            assert request.intent in row.intents, name
            assert isinstance(request.target, RepositoryWrite | PromotionWrite | DiscardWrite), name

    def test_engagement_authoring_builders_resolve_the_repo_root_argument(self, roots) -> None:
        engagement, _ = roots
        for name, row in MUTATION_TOOL_MANIFEST.items():
            if row.intents != ("engagement_authoring",):
                continue
            request = row.build_request({"repo_root": str(engagement)})
            assert isinstance(request.target, RepositoryWrite), name
            assert request.target.root == engagement, name

    def test_promotion_builder_carries_source_and_destination(self, roots) -> None:
        engagement, enterprise = roots
        row = MUTATION_TOOL_MANIFEST["artifact_promote_to_enterprise"]
        request = row.build_request({"repo_root": str(engagement), "enterprise_root": str(enterprise)})
        assert request == MutationRequest("promotion", PromotionWrite(engagement, enterprise))

    def test_save_changes_builder_switches_intent_on_target(self, roots) -> None:
        engagement, enterprise = roots
        row = MUTATION_TOOL_MANIFEST["artifact_save_changes"]
        assert row.build_request({"target": "engagement"}) == MutationRequest(
            "engagement_authoring", RepositoryWrite(engagement)
        )
        assert row.build_request({"target": "enterprise"}) == MutationRequest(
            "enterprise_save", RepositoryWrite(enterprise)
        )

    def test_withdraw_builder_distinguishes_pending_remote(self, roots, monkeypatch: pytest.MonkeyPatch) -> None:
        _, enterprise = roots
        row = MUTATION_TOOL_MANIFEST["artifact_withdraw_changes"]
        request = row.build_request({})
        assert request == MutationRequest(
            "enterprise_discard", DiscardWrite(enterprise, pending_remote=False)
        )

        class _PendingState:
            def is_pending(self) -> bool:
                return True

        monkeypatch.setattr(
            "src.infrastructure.git.enterprise_sync_state.load", lambda root: _PendingState()
        )
        pending_request = row.build_request({})
        assert pending_request.target == DiscardWrite(enterprise, pending_remote=True)
