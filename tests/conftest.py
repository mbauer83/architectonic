"""Session-wide collection hooks.

Cross-test isolation ordering: a handful of tests mutate *process-global* state that other
tests rely on staying stable, in ways a per-test fixture can't undo. Rather than skip or
weaken those tests, they are pinned to run strictly last so nothing scheduled afterward can
observe the mutation — this preserves full parallelism for the rest of the suite instead of
serializing everything.
"""

from __future__ import annotations

import fcntl
import os

import pytest

# Test ids (substring match against nodeid) that must run after everything else. Currently:
# TestRestartEquivalentRebootstrap calls importlib.reload(src.infrastructure.app_bootstrap),
# which replaces that module's top-level function objects (e.g. runtime_catalogs_dependency,
# module_registry_dependency) in place. Router modules already imported at collection time
# hold FastAPI `Depends(...)` bound to the pre-reload objects, so any other test on the same
# xdist worker that re-imports app_bootstrap fresh (to build `dependency_overrides`) after
# this one has run would get a *different* object identity than the router's — the override
# then silently misses and the real (uninstalled-registry) dependency runs instead. Pytest's
# default `--dist=load` xdist scheduler dispatches collected items in collection order to
# whichever worker next asks for work, so a test placed last in the full collected list is
# guaranteed to be the last test executed in the entire session, on any worker — no other
# test can run afterward to observe the mutation.
_RUN_LAST_SUBSTRINGS = (
    "tests/cli/test_arch_import_guidance.py::TestRestartEquivalentRebootstrap",
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    run_last = [item for item in items if any(needle in item.nodeid for needle in _RUN_LAST_SUBSTRINGS)]
    if not run_last:
        return
    remaining = [item for item in items if item not in run_last]
    items[:] = remaining + run_last


@pytest.fixture(autouse=True)
def _reset_installed_mutation_executor():
    """No test may leak an installed AuthorizedMutationExecutor to its successors.

    Tests that install one (over their own tmp roots and mode flags) would
    otherwise poison later tests on the same worker with foreign-root snapshots —
    every later REST/MCP write then 403s as target_not_engagement_root. Resetting
    after every test restores the dynamic workspace-default composition.
    """
    yield
    from src.infrastructure.write.mutation_executor_registry import _reset_executor_for_test

    _reset_executor_for_test()

# ── Credential-store isolation (MANDATORY, suite-wide) ───────────────────────
# INCIDENT GUARD (2026-07-20): a test placed outside tests/assurance//
# tests/integration/ called `init_store`, which wrote a freshly generated key
# through the REAL OS credential backend and overwrote the live assurance
# store's `db-encryption-key` and `db-recovery-key` — permanently locking the
# real store. No test may EVER reach the real credential backend, regardless
# of where the test file lives, so the in-memory replacement is installed
# autouse at the session root (the per-package fixtures in tests/assurance/
# and tests/integration/ remain as redundant local layers).


class _InMemoryCredentialBackend:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, account: str) -> str | None:
        return self._store.get(account)

    def set(self, account: str, value: str) -> None:
        self._store[account] = value

    def delete(self, account: str) -> None:
        self._store.pop(account, None)


@pytest.fixture(autouse=True)
def _global_in_memory_credential_store():
    from src.infrastructure.assurance import _credential_store

    previous = _credential_store._backend
    _credential_store._backend = _InMemoryCredentialBackend()
    yield
    _credential_store._backend = previous


# SECOND INCIDENT (2026-07-28): the fixture above was defeated and the live store's
# `db-encryption-key` was overwritten a second time — the ciphertext survived, the key did not.
#
# Why the fixture alone is not enough: it *sets* `_credential_store._backend`, and
# `_credential_store.reset_backend()` *clears* the same global. Tests that legitimately exercise
# backend selection call it, and the next `_get_backend()` on that worker re-selects the real OS
# backend — for every test that follows, not just the one that reset it. The protection was
# order-dependent, which is to say it was not protection.
#
# So the suite now also fails closed at the source: while this variable is set, no real backend
# can be selected at all, whatever happens to the cached global. Session-scoped and never
# unset — a test needing a working credential store installs an explicit fake.
@pytest.fixture(autouse=True, scope="session")
def _forbid_real_credential_backend(tmp_path_factory):
    from src.infrastructure.assurance._credential_store import (
        _CREDENTIALS_DIR_ENV,
        _FORBID_REAL_BACKEND_ENV,
    )

    os.environ[_FORBID_REAL_BACKEND_ENV] = "1"
    # Belt AND braces. The forbid flag protects backend selection inside THIS process;
    # it has now been bypassed three times by writers it cannot see (subprocesses,
    # paths around selection). Redirecting the credential DIRECTORY itself means even
    # an escaped writer lands in a throwaway tmp dir — subprocesses inherit the env,
    # and any test that deliberately replaces a child's env must set both variables.
    os.environ[_CREDENTIALS_DIR_ENV] = str(tmp_path_factory.mktemp("hermetic-credentials"))
    yield


# ── The PlantUML toolchain is a bounded resource, and the bound is here ───────
#
# Each render shells out to a cold JVM (which in turn runs GraphViz) under a fixed 60-second budget.
# `addopts` says `-n auto`: twenty workers on this box, so up to twenty simultaneous JVM starts, and
# the budget does not survive that. Measured: the render-touching selection was 31 failures at twenty
# workers and 1,863 passed at six. The gate command has always prefixed
# `PYTEST_XDIST_AUTO_NUM_WORKERS=6` for this reason, which made the *documented* invocation safe and
# the default one report three dozen defects that are not there.
#
# The bound belongs at the resource, not at the worker pool and not at a list of tests:
#
# * capping workers would slow the pure-Python majority of 8,600 tests to protect a few hundred;
# * `--dist loadgroup` would change the scheduler for the whole session, and the run-last guarantee
#   above is written against `--dist load`'s dispatch order;
# * classifying tests — by marker or by scanning their source for a render call — puts the knowledge
#   in a second place, and the failure mode of forgetting is a flake that reads as a product defect.
#
# `puml_runtime` starts the JVM in exactly one place. Wrapping that one call needs no classification,
# cannot be forgotten by a new test, and holds the lock for the render rather than for the whole test,
# so everything else in that test still runs in parallel.
#
# The lock is taken *before* `subprocess.run`, so the 60-second budget starts after the wait: queueing
# costs wall-clock, never a timeout. The lock file lives in the parent of this worker's base temp
# directory, which is the directory xdist shares between workers — a per-worker path would serialise
# each worker against itself and nothing else.


@pytest.fixture(scope="session", autouse=True)
def _bound_concurrent_plantuml_renders(tmp_path_factory: pytest.TempPathFactory):
    """One PlantUML subprocess at a time, across every xdist worker in the session."""
    from src.infrastructure.rendering import puml_runtime

    lock_path = tmp_path_factory.getbasetemp().parent / "plantuml-render.lock"
    real_subprocess = puml_runtime.subprocess

    class _OneRenderAtATime:
        """`subprocess` as this module uses it, with `run` serialised.

        Delegates everything else — the module also reads `subprocess.TimeoutExpired` — so this stays
        correct if the adapter grows a second use rather than silently losing one.
        """

        def run(self, *args: object, **kwargs: object) -> object:
            with lock_path.open("a+") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    return real_subprocess.run(*args, **kwargs)
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)

        def __getattr__(self, name: str) -> object:
            return getattr(real_subprocess, name)

    puml_runtime.subprocess = _OneRenderAtATime()
    try:
        yield
    finally:
        puml_runtime.subprocess = real_subprocess
