"""AuthorizedMutationExecutor: one queue submission, one gate acquisition, fresh
snapshot re-check inside the worker, typed rejection without submission, and a
bounded per-call authorization overhead (writes are serialized and I/O-bound;
authorization must never become the queue's bottleneck)."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import TypeVar

import pytest

from src.application.mutation_authorization import (
    AuthorizationSnapshot,
    MutationRejected,
    MutationRequest,
    RepositoryWrite,
    SyncHealth,
)
from src.infrastructure.concurrency.single_writer_queue import SingleWriterQueue
from src.infrastructure.workspace.mutation_gate import WorkspaceMutationGate
from src.infrastructure.write.authorized_mutation_executor import AuthorizedMutationExecutor
from src.infrastructure.write.workspace_authorization import WorkspaceAuthorizationSnapshots

_T = TypeVar("_T")

_RESULT_TIMEOUT_S = 10.0


class _MutableProvider:
    """Snapshot provider whose read-only flag tests can flip between checks."""

    def __init__(self, engagement_root: Path, enterprise_root: Path) -> None:
        self.read_only = False
        self._engagement_root = engagement_root.resolve()
        self._enterprise_root = enterprise_root.resolve()

    def snapshot(self) -> AuthorizationSnapshot:
        return AuthorizationSnapshot(
            engagement_root=self._engagement_root,
            enterprise_root=self._enterprise_root,
            admin_mode=False,
            read_only=self.read_only,
            gate_block=None,
            sync_health=SyncHealth(),
        )


class _CountingGate(WorkspaceMutationGate):
    def __init__(self) -> None:
        super().__init__()
        self.acquisitions = 0

    def writing(self):
        self.acquisitions += 1
        return super().writing()


class _Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.engagement = tmp_path / "engagements" / "ENG-EXE" / "architecture-repository"
        self.enterprise = tmp_path / "enterprise-repository"
        self.engagement.mkdir(parents=True)
        self.enterprise.mkdir(parents=True)
        self.provider = _MutableProvider(self.engagement, self.enterprise)
        self.gate = _CountingGate()
        self.queue = SingleWriterQueue("test-authorized-executor")
        self.submissions: list[str] = []
        self.executor = AuthorizedMutationExecutor(
            self.provider, submitter=self._submit, gate=self.gate
        )

    def _submit(self, operation_name: str, operation: Callable[[], _T]) -> Future[_T]:
        self.submissions.append(operation_name)
        return self.queue.submit(operation)

    def engagement_request(self) -> MutationRequest:
        return MutationRequest("engagement_authoring", RepositoryWrite(self.engagement))


@pytest.fixture()
def harness(tmp_path: Path):
    h = _Harness(tmp_path)
    yield h
    h.queue.shutdown()


class TestSingleSubmissionSingleGate:
    def test_success_path_is_one_submission_one_gate_acquisition(self, harness: _Harness) -> None:
        gate_held_during_operation: list[bool] = []

        def operation() -> str:
            gate_held_during_operation.append(harness.gate.acquisitions == 1)
            return "written"

        future = harness.executor.submit(harness.engagement_request(), operation, operation_name="probe_write")
        assert future.result(timeout=_RESULT_TIMEOUT_S) == "written"
        assert harness.submissions == ["probe_write"]
        assert harness.gate.acquisitions == 1
        assert gate_held_during_operation == [True]
        assert harness.queue.max_observed_in_flight == 1

    def test_run_completes_without_nested_wait(self, harness: _Harness) -> None:
        """Timeout-bounded: a second run after the first must not deadlock on the
        single-worker queue (the executor owns the only submission)."""
        started = time.monotonic()
        for round_index in range(3):
            value = harness.executor.run(
                harness.engagement_request(), lambda: round_index, operation_name="probe_write"
            )
            assert value == round_index
        assert time.monotonic() - started < _RESULT_TIMEOUT_S
        assert len(harness.submissions) == 3
        assert harness.queue.max_observed_in_flight == 1


class TestRejectionBeforeSubmission:
    def test_denied_request_never_reaches_the_queue(self, harness: _Harness) -> None:
        harness.provider.read_only = True
        with pytest.raises(MutationRejected) as excinfo:
            harness.executor.run(harness.engagement_request(), lambda: "never", operation_name="probe_write")
        assert excinfo.value.denial.code == "read_only"
        assert harness.submissions == []
        assert harness.gate.acquisitions == 0

    def test_enterprise_target_rejected_on_standard_authoring(self, harness: _Harness) -> None:
        request = MutationRequest("engagement_authoring", RepositoryWrite(harness.enterprise))
        with pytest.raises(MutationRejected) as excinfo:
            harness.executor.run(request, lambda: "never", operation_name="probe_write")
        assert excinfo.value.denial.code == "enterprise_target_forbidden"
        assert harness.submissions == []


class TestFreshRecheckInsideWorker:
    def test_authority_change_between_submit_and_execution_rejects(self, harness: _Harness) -> None:
        """The worker re-checks a FRESH snapshot: authority revoked while the job
        sits in the queue must reject the execution, not run it."""
        import threading

        first_job_started = threading.Event()
        release_first_job = threading.Event()

        def blocker() -> None:
            first_job_started.set()
            assert release_first_job.wait(timeout=_RESULT_TIMEOUT_S)

        harness.queue.submit(blocker)
        assert first_job_started.wait(timeout=_RESULT_TIMEOUT_S)
        future = harness.executor.submit(
            harness.engagement_request(), lambda: "should not run", operation_name="probe_write"
        )
        harness.provider.read_only = True
        release_first_job.set()
        with pytest.raises(MutationRejected) as excinfo:
            future.result(timeout=_RESULT_TIMEOUT_S)
        assert excinfo.value.denial.code == "read_only"
        assert harness.gate.acquisitions == 0

    def test_operation_failure_releases_gate_for_next_write(self, harness: _Harness) -> None:
        def failing() -> None:
            raise RuntimeError("write exploded")

        with pytest.raises(RuntimeError):
            harness.executor.run(harness.engagement_request(), failing, operation_name="probe_write")
        assert harness.executor.run(
            harness.engagement_request(), lambda: "recovered", operation_name="probe_write"
        ) == "recovered"


class TestAuthorizationOverheadBounded:
    def test_snapshot_plus_authorize_is_model_size_independent_and_cheap(self, tmp_path: Path) -> None:
        """Writes are serialized and file-I/O-bound; per-call authorization must stay
        far below that. A generous 500µs average bound catches any accidental
        O(model-size) work sneaking into the snapshot or policy path."""
        from src.application.mutation_policy import authorize

        engagement = tmp_path / "engagements" / "ENG-PRF" / "architecture-repository"
        enterprise = tmp_path / "enterprise-repository"
        engagement.mkdir(parents=True)
        enterprise.mkdir(parents=True)
        provider = WorkspaceAuthorizationSnapshots(
            engagement_root=engagement,
            enterprise_root=enterprise,
            admin_mode=False,
            read_only=False,
            gate=WorkspaceMutationGate(),
        )
        request = MutationRequest("engagement_authoring", RepositoryWrite(engagement))
        rounds = 1000
        started = time.perf_counter()
        for _ in range(rounds):
            authorize(provider.snapshot(), request)
        average_s = (time.perf_counter() - started) / rounds
        assert average_s < 0.0005, f"authorization averaged {average_s * 1e6:.0f}µs per call"
