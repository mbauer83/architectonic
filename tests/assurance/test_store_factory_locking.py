"""Acquiring an assurance bundle must not block on itself or on the credential backend.

The bundle registry and this process's authorization flag are separate pieces of state. When one
non-reentrant lock guarded both, acquiring a bundle deadlocked: the registry lock was held while
the store was opened, and opening the store reads the authorization flag. The deadlocked thread
kept holding the registry lock, so every later assurance request queued behind it forever — one
leaked worker thread per request until the server's thread pool was exhausted and unrelated
endpoints stopped answering.

Every test here goes through `get_assurance_bundle`, which is what makes them catch it: calling
`try_auto_unlock` directly, as the policy tests do, never takes the registry lock and so cannot
reproduce the failure.

Each test runs the call on a worker thread with a deadline, so a regression fails the test rather
than hanging the suite.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Iterator

import pytest

from src.infrastructure.assurance import store_factory

#: Generous next to the work involved (a stubbed store build), short enough that a deadlock is
#: reported as a failure quickly.
DEADLINE_SECONDS = 10.0


class _FakeStore:
    def __init__(self) -> None:
        self.unlocked = False
        self.unlock_calls = 0

    def is_unlocked(self) -> bool:
        return self.unlocked

    def unlock(self) -> None:
        self.unlock_calls += 1
        self.unlocked = True

    def lock(self) -> None:
        self.unlocked = False


def _run_with_deadline(call: object, *, deadline: float = DEADLINE_SECONDS) -> None:
    """Run `call` on a worker thread and fail if it has not returned by the deadline."""
    error: list[BaseException] = []

    def _target() -> None:
        try:
            call()  # type: ignore[operator]
        except BaseException as exc:  # noqa: BLE001
            error.append(exc)

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout=deadline)
    assert not worker.is_alive(), (
        f"acquiring the bundle did not return within {deadline}s — it is blocked on a lock"
    )
    if error:
        raise error[0]


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The registry and the authorization flag are process state, so they must not leak."""
    monkeypatch.setattr(store_factory, "_instances", {})
    monkeypatch.setattr(store_factory, "_last_auto_unlock_attempt", {})
    store_factory.revoke_process_authorization()
    yield
    store_factory.revoke_process_authorization()


@pytest.fixture()
def stub_build(monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    """Replace bundle construction, so these tests exercise locking and nothing else."""
    store = _FakeStore()

    def _build(workspace: Path, **_kwargs: object) -> store_factory._AssuranceBundle:
        return store_factory._AssuranceBundle(  # noqa: SLF001
            store,  # type: ignore[arg-type]
            archive=None,  # type: ignore[arg-type]
            store_backend="private-git",
            signals_backend="public-sqlite",
            archive_backend="standard",
            store_scope=workspace / ".arch-assurance-git",
        )

    monkeypatch.setattr(store_factory, "_build_bundle", _build)
    monkeypatch.setattr(
        store_factory.storage_settings, "storage_assurance_activation_policy", lambda: "persistent",
    )
    return store


def _gate(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    from src.infrastructure.assurance import _credential_store as creds

    monkeypatch.setattr(creds, "get", lambda _account: value)


class TestAcquiringABundleCompletes:
    def test_the_first_acquisition_returns(
        self, monkeypatch: pytest.MonkeyPatch, stub_build: _FakeStore, tmp_path: Path
    ) -> None:
        """The build path opens the store, and opening it reads the authorization flag."""
        _gate(monkeypatch, "1")

        _run_with_deadline(lambda: store_factory.get_assurance_bundle(tmp_path))

        assert stub_build.unlocked, "an activated store should have been opened"

    def test_a_later_acquisition_returns(
        self, monkeypatch: pytest.MonkeyPatch, stub_build: _FakeStore, tmp_path: Path
    ) -> None:
        """The cached path retries the unlock, which reads the authorization flag too."""
        _gate(monkeypatch, None)
        _run_with_deadline(lambda: store_factory.get_assurance_bundle(tmp_path))
        monkeypatch.setitem(store_factory._last_auto_unlock_attempt, str(tmp_path.resolve()), 0)  # noqa: SLF001
        _gate(monkeypatch, "1")

        _run_with_deadline(lambda: store_factory.get_assurance_bundle(tmp_path))

        assert stub_build.unlocked, "the retry should have opened the now-activated store"

    def test_acquisition_returns_under_the_manual_policy(
        self, monkeypatch: pytest.MonkeyPatch, stub_build: _FakeStore, tmp_path: Path
    ) -> None:
        """The manual policy is the path that reads the authorization flag on every attempt."""
        monkeypatch.setattr(
            store_factory.storage_settings, "storage_assurance_activation_policy", lambda: "manual",
        )
        _gate(monkeypatch, "1")

        _run_with_deadline(lambda: store_factory.get_assurance_bundle(tmp_path))

        assert not stub_build.unlocked, "an unauthorized process must not open the store"

    def test_acquisition_returns_for_an_authorized_process_under_the_manual_policy(
        self, monkeypatch: pytest.MonkeyPatch, stub_build: _FakeStore, tmp_path: Path
    ) -> None:
        """The full manual path: the flag is read and acted on, then the gate is read."""
        monkeypatch.setattr(
            store_factory.storage_settings, "storage_assurance_activation_policy", lambda: "manual",
        )
        _gate(monkeypatch, "1")
        store_factory.authorize_process()

        _run_with_deadline(lambda: store_factory.get_assurance_bundle(tmp_path))

        assert stub_build.unlocked, "an authorized process should have opened the store"


class TestTheCredentialBackendCannotStallOtherRequests:
    def test_a_hanging_gate_read_does_not_block_a_second_caller(
        self, monkeypatch: pytest.MonkeyPatch, stub_build: _FakeStore, tmp_path: Path
    ) -> None:
        """A credential backend that never answers must cost one request, not the whole process.

        This is what the registry lock must not span: an unreachable keychain used to take every
        assurance surface down with it, which is how a locked store came to look inexplicable.
        """
        from src.infrastructure.assurance import _credential_store as creds

        entered = threading.Event()
        release = threading.Event()

        def _hangs(_account: str) -> str | None:
            entered.set()
            release.wait(timeout=DEADLINE_SECONDS)
            return "1"

        monkeypatch.setattr(creds, "get", _hangs)
        stalled = threading.Thread(
            target=lambda: store_factory.get_assurance_bundle(tmp_path), daemon=True
        )
        stalled.start()
        assert entered.wait(timeout=DEADLINE_SECONDS), "the gate read was never reached"

        try:
            _run_with_deadline(lambda: store_factory.get_assurance_bundle(tmp_path))
        finally:
            release.set()
            stalled.join(timeout=DEADLINE_SECONDS)


class TestAuthorizationIsReadableWhileTheRegistryIsBusy:
    def test_reading_the_flag_does_not_wait_on_bundle_construction(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Status surfaces read the flag; a slow build must not make them hang."""
        entered = threading.Event()
        release = threading.Event()

        def _slow_build(_workspace: Path, **_kwargs: object) -> store_factory._AssuranceBundle:
            entered.set()
            release.wait(timeout=DEADLINE_SECONDS)
            return store_factory._AssuranceBundle(  # noqa: SLF001
                _FakeStore(),  # type: ignore[arg-type]
                archive=None,  # type: ignore[arg-type]
                store_backend="pocketbase",
                signals_backend="public-sqlite",
                archive_backend="standard",
                store_scope=_workspace / ".arch-assurance",
            )

        monkeypatch.setattr(store_factory, "_build_bundle", _slow_build)
        building = threading.Thread(
            target=lambda: store_factory.get_assurance_bundle(tmp_path), daemon=True
        )
        building.start()
        assert entered.wait(timeout=DEADLINE_SECONDS), "the build was never reached"

        try:
            _run_with_deadline(store_factory.is_process_authorized)
        finally:
            release.set()
            building.join(timeout=DEADLINE_SECONDS)
