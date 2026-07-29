"""A container has nobody inside it to unlock the store, so it must say so in its configuration.

`activation_policy` defaults to `manual`: a newly started process starts locked, and `unlock`
authorizes the process that is running. That is right for a workstation, where a restart is already a
human act.

A container inverts it. The process that serves assurance is `arch-backend`, started by the last line
of the entrypoint — and `arch-assurance unlock` runs several steps earlier, when that process does not
exist. So the gate gets set and nothing gets authorized, and under `manual` the store would be locked
after every `docker compose up`, however many times the entrypoint ran `unlock`.

These assertions read the shipped entrypoint and env template as text, because that is the artefact
an operator deploys; a unit test of the settings writer would pass while the container still shipped
the wrong posture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "docker" / "entrypoint.sh"
ENV_TEMPLATE = ROOT / ".env.example"


@pytest.fixture(scope="module")
def entrypoint() -> str:
    return ENTRYPOINT.read_text(encoding="utf-8")


class TestTheContainerAssertsItsOwnPosture:
    def test_the_entrypoint_sets_an_activation_policy(self, entrypoint: str) -> None:
        """Inheriting the code default would leave the store locked with nobody to open it."""
        assert "--activation-policy" in entrypoint

    def test_it_defaults_to_persistent(self, entrypoint: str) -> None:
        assert 'ARCH_ASSURANCE_ACTIVATION_POLICY:-persistent' in entrypoint

    def test_the_operator_can_override_it(self, entrypoint: str) -> None:
        """`manual` remains available for a deployment that wants the ceremony — the point is that
        the choice is stated, not that it is forced."""
        assert "ARCH_ASSURANCE_ACTIVATION_POLICY" in ENV_TEMPLATE.read_text(encoding="utf-8")

    def test_the_policy_is_asserted_before_the_backend_starts(self, entrypoint: str) -> None:
        """Order is the whole defect: a policy written after `exec arch-backend` would never be read
        by the process it governs."""
        assert entrypoint.index("--activation-policy") < entrypoint.index("exec arch-backend")


class TestTheEntrypointDoesNotClaimWhatItCannotDo:
    def test_it_no_longer_says_unlock_covers_future_restarts(self, entrypoint: str) -> None:
        """It said "auto-unlock active for future restarts", which described the behaviour before the
        activation policy existed. What opens a future process is the policy, not this command."""
        assert "auto-unlock active for future restarts" not in entrypoint

    def test_it_warns_when_the_policy_will_leave_the_backend_locked(self, entrypoint: str) -> None:
        """Under `manual` the operator has to act, and finding that out from a locked GUI is worse
        than being told on start."""
        assert "will start LOCKED" in entrypoint
