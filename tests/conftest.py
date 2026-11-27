"""Session-wide collection hooks.

Cross-test isolation ordering: a handful of tests mutate *process-global* state that other
tests rely on staying stable, in ways a per-test fixture can't undo. Rather than skip or
weaken those tests, they are pinned to run strictly last so nothing scheduled afterward can
observe the mutation — this preserves full parallelism for the rest of the suite instead of
serializing everything.
"""

from __future__ import annotations

import faulthandler
import fcntl
import json
import os
import pathlib
import sys
import tempfile

import pytest

from tests.support.shard_durations import duration_coverage

#: Fixtures shared across directories, kept out of this file so it stays a list of process guards.
pytest_plugins = ["tests.support.rendered_model_fixtures"]

#: How long a whole run may take before it is treated as stuck, in seconds.
#:
#: The suite is ~4:30 on twenty workers, so the controller's budget is a four-fold margin: a run past
#: it is not slow, it is stopped. Absolute rather than idle-based because `faulthandler` offers no
#: idle timer, and an absolute budget with that much headroom costs nothing on a healthy run.
#:
#: A worker dumps *earlier*, and without exiting, so its stack is in the log before the controller
#: gives up. That asymmetry is the whole point: the controller's own stack says only that it is
#: waiting for workers — which is true and useless — and the question is what the workers are doing.
_STUCK_AFTER_SECONDS = 20 * 60
_WORKER_DUMPS_AFTER_SECONDS = 8 * 60


def pytest_configure(config: pytest.Config) -> None:
    """Turn a hung session into stack dumps and a failure, in every process it could hang in.

    A run has stalled repeatedly with every worker idle and the controller waiting — no test
    executing, so `faulthandler_timeout`, which is per-test, never fires. There is nothing to
    interrupt and nothing to read: the run simply never ends, and once it did so *after* a real
    failure, which it then never printed. A stall that hides a result is worse than a slow one.

    Armed here rather than in a fixture because `pytest_configure` runs in the controller as well as
    in each worker, and both halves of the wait have to be visible to say which one is stuck.
    """
    worker = getattr(config, "workerinput", {}).get("workerid") if hasattr(config, "workerinput") else None
    if worker is None:
        faulthandler.dump_traceback_later(_STUCK_AFTER_SECONDS, exit=True)
        config.add_cleanup(faulthandler.cancel_dump_traceback_later)
        return

    # To a file, not to stderr. A worker's stderr is buffered by the controller and forwarded when
    # the worker reports — which is exactly what a stalled worker never does, so a dump written
    # there is a dump nobody ever sees. On disk it can be read *while* the run is stuck, which is
    # the only moment the answer exists.
    dump = pathlib.Path(tempfile.gettempdir()) / f"arch-pytest-stall-{worker}.stack"
    handle = dump.open("w", encoding="utf-8")
    faulthandler.dump_traceback_later(
        _WORKER_DUMPS_AFTER_SECONDS, repeat=True, exit=False, file=handle
    )

    def _stand_down() -> None:
        faulthandler.cancel_dump_traceback_later()
        handle.close()
        dump.unlink(missing_ok=True)

    config.add_cleanup(_stand_down)

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


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    _refuse_a_split_on_stale_durations(config, items)
    run_last = [item for item in items if any(needle in item.nodeid for needle in _RUN_LAST_SUBSTRINGS)]
    if not run_last:
        return
    remaining = [item for item in items if item not in run_last]
    items[:] = remaining + run_last


def _refuse_a_split_on_stale_durations(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Fail a sharded run whose `.test_durations` no longer names most of the suite (B142).

    Runs before pytest-split deselects, so it sees every collected test. Only in a run without xdist
    workers: a worker that stops at collection surfaces as an internal error of the controller's
    scheduler and the reason is lost. CI therefore asks in a collect-only step of its own
    (`pytest -n 0 --collect-only --splits 3 --group 1`, ~15 s), before any shard starts.
    """
    if not config.getoption("splits", default=None) or hasattr(config, "workerinput"):
        return
    durations_path = config.getoption("durations_path")
    try:
        recorded = json.loads(pathlib.Path(durations_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        recorded = {}
    coverage = duration_coverage((item.nodeid for item in items), recorded)
    if coverage.is_stale:
        raise pytest.UsageError(coverage.refusal(durations_path))


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
# can be selected at all, whatever happens to the cached global. Never unset — a test needing a
# working credential store installs an explicit fake.
#
# THIRD GAP (2026-11-13): both guards were *fixtures*, and fixtures start after collection. A test
# module that builds the module registry at import time — for a parameter list — probed the
# confidential-store capability during collection, which selected the real Windows credential
# backend, read the developer's live store key, and cached a registry that included the assurance
# diagram types for the rest of the worker. The fixture above then restored that real backend as
# "previous" after every test. Reads only, but it made a developer box register what CI's store-less
# job does not, which is how a defect CI failed 104 times passed every local run.
#
# So the seal is applied when this file is imported: before any test module is, in the controller
# and in every xdist worker. The redirected credential directory is belt and braces — the forbid
# flag protects selection inside this process, and has been bypassed by writers it cannot see
# (subprocesses, paths around selection); an escaped writer lands in a throwaway directory, since
# subprocesses inherit the environment. A test that replaces a child's env must set both variables.
def _seal_the_real_credential_backend() -> None:
    import atexit
    import shutil

    from src.infrastructure.assurance import _credential_store
    from src.infrastructure.assurance._credential_store import (
        _CREDENTIALS_DIR_ENV,
        _FORBID_REAL_BACKEND_ENV,
    )

    os.environ[_FORBID_REAL_BACKEND_ENV] = "1"
    credentials = tempfile.mkdtemp(prefix="hermetic-credentials-")
    atexit.register(shutil.rmtree, credentials, ignore_errors=True)
    os.environ[_CREDENTIALS_DIR_ENV] = credentials
    _credential_store._backend = _InMemoryCredentialBackend()


_seal_the_real_credential_backend()


# ── A test store's key costs one hash, not 256,000 ────────────────────────────
# Applied at import, beside the credential seal and for the same reason: before any test module
# builds a store. Why it is sound is in the module.
from tests.support.store_key_derivation import cheapen_test_store_key_derivation  # noqa: E402

cheapen_test_store_key_derivation()


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
# The lock is taken *before* `subprocess.run`, so the budget starts after the wait: queueing costs
# wall-clock, never a timeout. The lock file lives in the parent of this worker's base temp directory,
# which is the directory xdist shares between workers — a per-worker path would serialise each worker
# against itself and nothing else.
#
# The budget is also widened, and the two go together. Serialising the JVMs removed 30 of the 31
# failures; the last was a cold JVM that still exceeded 60 seconds while nineteen other workers ran
# Python flat out. 60 is a *production* budget — a server answering one preview request — and applying
# it to a deliberately saturated box measures the box, not the renderer. Widened here rather than in
# `puml_runtime` because production's budget is a product decision with latency consequences, and
# nothing has asked for it to change; a config knob added for a test-only need is its own smell.
_RENDER_BUDGET_SECONDS = 300


def _plantuml_lock_path(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    return tmp_path_factory.getbasetemp().parent / "plantuml-render.lock"


def _one_render_at_a_time(real_subprocess: object, lock_path: pathlib.Path) -> object:
    """*real_subprocess* with `run` serialised across the session under the widened budget."""

    class _OneRenderAtATime:
        """`subprocess` as this module uses it, with `run` serialised.

        Delegates everything else — the module also reads `subprocess.TimeoutExpired` — so this stays
        correct if the adapter grows a second use rather than silently losing one.
        """

        def run(self, *args: object, **kwargs: object) -> object:
            with lock_path.open("a+") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    return real_subprocess.run(*args, **{**kwargs, "timeout": _RENDER_BUDGET_SECONDS})
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)

        def __getattr__(self, name: str) -> object:
            return getattr(real_subprocess, name)

    return _OneRenderAtATime()


@pytest.fixture(scope="session", autouse=True)
def _bound_concurrent_plantuml_renders(tmp_path_factory: pytest.TempPathFactory):
    """One PlantUML subprocess at a time, across every xdist worker in the session."""
    from src.infrastructure.rendering import puml_runtime

    real_subprocess = puml_runtime.subprocess
    puml_runtime.subprocess = _one_render_at_a_time(real_subprocess, _plantuml_lock_path(tmp_path_factory))
    try:
        yield
    finally:
        puml_runtime.subprocess = real_subprocess


@pytest.fixture(autouse=True)
def _each_test_draws_its_own_pictures():
    """No test is handed a picture another drew (`plantuml_pictures`): a test that fakes the renderer must
    see its fake asked, whatever drew the same body earlier on the same worker."""
    from src.application.plantuml_pictures import DRAWN

    DRAWN.forget()
    yield
    DRAWN.forget()


@pytest.fixture
def plantuml_syntax_check(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Let this test run the real PlantUML syntax check, under the same bound as every render.

    The syntax check starts the JVM in a second place. `tests/tools` switches it off for its whole
    process (`ARCH_SKIP_PUML_SYNTAX`), so whether it runs depends on which conftest a worker has
    loaded. A test that is *about* the check asks for it here: switched on whatever was loaded, and
    queued behind the same lock instead of joining twenty other JVMs under a production timeout.
    """
    from src.application.verification import artifact_verifier_syntax

    monkeypatch.delenv("ARCH_SKIP_PUML_SYNTAX", raising=False)
    monkeypatch.setattr(
        artifact_verifier_syntax,
        "subprocess",
        _one_render_at_a_time(artifact_verifier_syntax.subprocess, _plantuml_lock_path(tmp_path_factory)),
    )


@pytest.fixture(autouse=True)
def _restore_root_logging():
    """No test may leave the root logger reconfigured for its successors.

    `arch_backend.main()` calls `logging.basicConfig(..., force=True)`, which *replaces* the root
    logger's handlers — by design, since it owns the process when run as a command. Called from a test,
    it takes that decision away from pytest's own logging and capture plugins for every test that
    follows on the same xdist worker.

    Three `test_unified_backend_runtime` tests asserting on captured output failed once in a full run
    and never in isolation, which is the signature. A run-last pin would not fix it: the problem is
    not ordering but that the mutation outlives the test, and the suite has 8,600 successors. Snapshot
    and restore is the narrow fix, and it costs a list copy per test.
    """
    import logging

    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    yield
    if list(root.handlers) != handlers or root.level != level:
        root.handlers[:] = handlers
        root.setLevel(level)


@pytest.fixture(autouse=True)
def _never_redirect_the_workers_stdio(monkeypatch: pytest.MonkeyPatch):
    """`arch-backend`'s background-TTY probe answers False under test, always.

    `arch_backend.main()` asks `_is_background_tty_job()` — `sys.stderr.isatty()` and a terminal
    process-group comparison — and on True calls `_redirect_stdio_to_backend_log`, which is
    `os.dup2(log_fd, sys.stdout.fileno())`. That is a **file-descriptor** redirect, so it does not end
    with the test: it repoints the xdist worker's fd 1 and fd 2 at a log file for every test that
    follows on that worker, and their captured output silently becomes empty.

    Which is exactly what was seen: two or three `test_unified_backend_runtime` tests failing per full
    run, a *different* two or three each time, all asserting on captured stdout, and every one of them
    passing in isolation. Restoring the root logger did not help because the damage is below logging.
    The probe reads the environment, so under pytest its answer is environment-dependent — pinning it
    is the fix, and it belongs here rather than in each test that happens to call `main()`.

    A test that wants the True branch monkeypatches the probe itself, which overrides this and is what
    `test_arch_backend_redirects_stdio_when_background_tty_job` already does — safely, because it
    stubs the redirect too.
    """
    module = sys.modules.get("src.infrastructure.backend.arch_backend")
    if module is not None:
        monkeypatch.setattr(module, "_is_background_tty_job", lambda: False)
    yield


@pytest.fixture(autouse=True)
def _no_test_leaves_an_embedding_encoder_cached():
    """No test may leave the semantic encoder cached for its successors.

    `semantic_provider_for` caches the process's encoder with `lru_cache`, deliberately: the weights
    are the same for every store a process serves and loading them costs 0.35s, so a backend serving
    two repository roots should read 30 MB once. Under xdist that cache outlives the test that filled
    it, and the next test on that worker gets a live encoder whether or not its own settings enabled
    one — so `semantic_provider_for` builds a real retriever over whatever store it was handed.

    Which is exactly what was seen: `test_startup_ordering` failing on
    `'_FakeIndex' object has no attribute 'entity_ids'`, in a run whose sharding happened to put it
    after the provider-wiring tests, and passing in isolation and in every earlier full run.

    Clearing after as well as before is the whole fix: the wiring tests already cleared on the way in,
    which protects them from their predecessors and their successors from nothing.
    """
    from src.infrastructure.search import provider

    provider._process_encoder.cache_clear()
    yield
    provider._process_encoder.cache_clear()


@pytest.fixture(autouse=True)
def _reset_rest_server_state():
    """No test may leave the REST layer's process state configured for its successors.

    `state.py` holds five module globals that `arch_backend.main()` and every router test set through
    `init_state`. Two of them are `_admin_mode` and `_read_only`: a test that initialises with
    `admin_mode=True` leaves the whole process in admin mode, so a later test asserting an enterprise
    write is *refused* gets a 200 and passes for the wrong reason.

    The sibling fixture above resets the installed mutation executor for the same reason; the state
    these globals hold was simply never included. Added while chasing a `test_unified_backend_runtime`
    flake that appears once per full run, on a different test each time, and never at module or
    directory scope — the signature of inherited process state. Whether it closes that flake or not,
    an `_admin_mode` that outlives its test is worth closing on its own.
    """
    yield
    from tests.support.rest_state import reset_state_for_test

    reset_state_for_test()
