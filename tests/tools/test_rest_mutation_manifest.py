"""Registry ⇔ manifest equality for the REST mutation surface, and the request builder per intent.

Every write-shaped operation the backend serves is either a manifested architecture-repository
mutator, an explicitly classified non-mutating operation, or an assurance-store operation (own
gating, excluded by design); both directions of the equality hold.

The equality is over **operation ids**. It used to be over ``(METHOD, path)`` pairs, and that is
precisely what made it possible for the copy of the path inside each handler to go stale while this
test stayed green — the handler's tuple was the one thing no path equality could see.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.mutation_authorization import (
    DiscardWrite,
    MutationRequest,
    PromotionWrite,
    RepositoryWrite,
)
from src.infrastructure.rest.route_policy import ROUTE_POLICY, UNSERVED_OPERATIONS
from src.infrastructure.rest.routers.rest_mutation_manifest import (
    ASSURANCE_ROUTE_PREFIX,
    NON_MUTATING_REST_OPERATIONS,
    REST_MUTATION_MANIFEST,
    build_rest_request,
)


def _served_write_shaped_operations() -> set[str]:
    """Write-shaped operations outside the assurance surface that are actually mounted."""
    return {
        row.operation_id
        for row in ROUTE_POLICY
        if row.is_write_shaped
        and not row.template.startswith(ASSURANCE_ROUTE_PREFIX)
        and row.operation_id not in UNSERVED_OPERATIONS
    }


class TestRestRegistryManifestEquality:
    def test_every_write_shaped_operation_is_classified(self) -> None:
        classified = set(REST_MUTATION_MANIFEST) | NON_MUTATING_REST_OPERATIONS
        assert _served_write_shaped_operations() - classified == set()

    def test_every_classified_operation_exists_in_the_route_policy(self) -> None:
        declared = {row.operation_id for row in ROUTE_POLICY}
        assert (set(REST_MUTATION_MANIFEST) | NON_MUTATING_REST_OPERATIONS) - declared == set()

    def test_manifest_and_non_mutating_sets_are_disjoint(self) -> None:
        assert not set(REST_MUTATION_MANIFEST) & NON_MUTATING_REST_OPERATIONS


class TestBuildRestRequest:
    @pytest.fixture
    def roots(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
        engagement = tmp_path / "engagements" / "ENG-RRM" / "architecture-repository"
        enterprise = tmp_path / "enterprise-repository"
        engagement.mkdir(parents=True)
        enterprise.mkdir(parents=True)
        monkeypatch.setattr("src.infrastructure.rest.routers.state.maybe_engagement_root", lambda: engagement)
        monkeypatch.setattr("src.infrastructure.rest.routers.state.maybe_enterprise_root", lambda: enterprise)
        monkeypatch.setattr(
            "src.infrastructure.rest.routers.state.get_both_roots", lambda: (engagement, enterprise)
        )
        return engagement, enterprise

    def test_every_manifest_row_builds_its_declared_intent(self, roots) -> None:
        for operation, intent in REST_MUTATION_MANIFEST.items():
            request = build_rest_request(operation)
            assert isinstance(request, MutationRequest), operation
            assert request.intent == intent, operation

    def test_engagement_operations_target_the_engagement_root(self, roots) -> None:
        engagement, _ = roots
        assert build_rest_request("entities_create_entity").target == RepositoryWrite(engagement)

    def test_promotion_operation_targets_both_roots(self, roots) -> None:
        engagement, enterprise = roots
        request = build_rest_request("promotion_execute_promotion")
        assert request.target == PromotionWrite(engagement, enterprise)

    def test_withdraw_operation_distinguishes_pending_remote(
        self, roots, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, enterprise = roots
        request = build_rest_request("sync_withdraw_enterprise")
        assert request.target == DiscardWrite(enterprise, pending_remote=False)

        class _Pending:
            def is_pending(self) -> bool:
                return True

        monkeypatch.setattr("src.infrastructure.git.enterprise_sync_state.load", lambda root: _Pending())
        assert build_rest_request("sync_withdraw_enterprise").target == DiscardWrite(
            enterprise, pending_remote=True
        )

    def test_an_unmanifested_operation_cannot_execute(self, roots) -> None:
        with pytest.raises(LookupError, match="classify the operation"):
            build_rest_request("entities_not_a_real_operation")

    def test_a_renamed_operation_id_fails_the_write_rather_than_only_a_test(self, roots) -> None:
        """Risk 12, from the other direction: the handler's authorization identity is checked at
        request time, so a stale one cannot reach the write queue with a wrong intent."""
        with pytest.raises(LookupError):
            build_rest_request("entities_edit_entity")  # the pre-migration spelling
