"""Operational-target orchestration: dedup, order, atomicity, resume semantics."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.application.deployment_upgrade.orchestrate import (
    apply_targets,
    dedupe_handles,
    evaluate_targets,
    order_handles,
)
from src.application.deployment_upgrade.ports import OperationalStepRegistry
from src.domain.repository.operational_upgrade import UpgradeTarget
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding


@dataclass
class _FakeUow:
    committed: bool = False
    rolled_back: bool = False
    writes: list[tuple[str, str]] = field(default_factory=list)

    def write_text(self, relative_path: str, content: str) -> None:
        self.writes.append((relative_path, content))

    def execute_sql(self, sql: str, parameters: tuple[object, ...] = ()) -> None:
        self.writes.append(("sql", sql))

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


@dataclass
class _FakeView:
    target: UpgradeTarget
    content: str | None = None

    def read_text(self, relative_path: str = "") -> str | None:
        return self.content

    def list_files(self, relative_glob: str) -> list[str]:
        return []

    def query_scalar(self, sql: str, parameters: tuple[object, ...] = ()) -> object | None:
        return None


@dataclass
class _FakeHandle:
    target: UpgradeTarget
    inspectable: bool = True
    content: str | None = None
    uow: _FakeUow = field(default_factory=_FakeUow)

    def view(self) -> _FakeView:
        return _FakeView(self.target, self.content)

    def begin(self) -> _FakeUow:
        return self.uow


def _target(kind: str, location: str, dependencies: tuple[str, ...] = ()) -> UpgradeTarget:
    return UpgradeTarget(
        kind=kind,  # type: ignore[arg-type]
        stable_id=f"{kind}:{location}",
        display_location=location,
        current_version=0,
        dependencies=dependencies,
    )


def _finding(step_id: str, *, auto: bool = True, blocks: bool = False) -> UpgradeFinding:
    return UpgradeFinding(
        step_id=step_id,
        finding_id=f"{step_id}-finding",
        location="/x",
        description="needs migration",
        severity="warning",
        auto_migratable=auto,
        rewrite_summary="rewrite" if auto else None,
        manual_instructions=None if auto else "manual",
        blocks_commit=blocks,
    )


@dataclass
class _FakeStep:
    id: str
    kind: str
    version: int = 1
    description: str = "fixture step"
    findings: list[UpgradeFinding] = field(default_factory=list)
    fail_with: Exception | None = None

    def detect(self, view: _FakeView) -> list[UpgradeFinding]:
        return list(self.findings)

    def apply(self, view: _FakeView, uow: _FakeUow, findings: list[UpgradeFinding]) -> list[AppliedFinding]:
        if self.fail_with is not None:
            raise self.fail_with
        uow.write_text("member", "migrated")
        return [AppliedFinding(finding=f, outcome="applied") for f in findings]


def _registry(*steps: _FakeStep) -> OperationalStepRegistry:
    registry = OperationalStepRegistry()
    for step in steps:
        registry.register(step)  # type: ignore[arg-type]
    return registry


class TestDiscoveryHygiene:
    def test_physical_dedup_keeps_one_handle_per_stable_id(self) -> None:
        a = _FakeHandle(_target("guidance_cache", "/cache"))
        b = _FakeHandle(_target("guidance_cache", "/cache"))
        assert dedupe_handles((a, b)) == (a,)

    def test_order_is_kind_order_then_dependencies(self) -> None:
        settings = _FakeHandle(_target("deployment_settings", "/s"))
        cache = _FakeHandle(_target("guidance_cache", "/c"))
        store = _FakeHandle(_target("assurance_sqlcipher", "/a"))
        ordered = order_handles((settings, store, cache))
        assert [h.target.kind for h in ordered] == [
            "guidance_cache",
            "assurance_sqlcipher",
            "deployment_settings",
        ]


class TestEvaluate:
    def test_no_registered_steps_means_current(self) -> None:
        reports = evaluate_targets((_FakeHandle(_target("guidance_cache", "/c")),), _registry())
        assert reports[0].state == "current"
        assert reports[0].results == ()

    def test_pending_and_blocked_states(self) -> None:
        pending = _FakeStep("s1", "guidance_cache", findings=[_finding("s1")])
        blocked = _FakeStep("s2", "signals_sqlite", findings=[_finding("s2", auto=False, blocks=True)])
        reports = evaluate_targets(
            (
                _FakeHandle(_target("guidance_cache", "/c")),
                _FakeHandle(_target("signals_sqlite", "/s")),
            ),
            _registry(pending, blocked),
        )
        by_kind = {r.target.kind: r for r in reports}
        assert by_kind["guidance_cache"].state == "pending"
        assert by_kind["signals_sqlite"].state == "blocked"

    def test_uninspectable_target_is_a_blocking_finding_and_never_assumed_current(self) -> None:
        handle = _FakeHandle(_target("assurance_sqlcipher", "/a"), inspectable=False)
        reports = evaluate_targets((handle,), _registry())
        assert reports[0].state == "uninspectable"
        assert reports[0].blocking
        assert reports[0].detail == "deployment readiness NOT certified"


class TestApply:
    def test_apply_commits_one_unit_per_target(self) -> None:
        handle = _FakeHandle(_target("guidance_cache", "/c"))
        step = _FakeStep("s1", "guidance_cache", findings=[_finding("s1")])
        reports, failed = apply_targets((handle,), _registry(step))
        assert failed is None
        assert reports[0].committed
        assert handle.uow.committed
        assert not handle.uow.rolled_back

    def test_step_exception_rolls_back_the_whole_unit(self) -> None:
        handle = _FakeHandle(_target("guidance_cache", "/c"))
        step = _FakeStep("s1", "guidance_cache", findings=[_finding("s1")], fail_with=RuntimeError("boom"))
        reports, failed = apply_targets((handle,), _registry(step))
        assert failed == handle.target.stable_id
        assert handle.uow.rolled_back
        assert not handle.uow.committed
        assert reports[0].has_errors

    def test_later_targets_are_not_attempted_after_a_failure(self) -> None:
        failing = _FakeHandle(_target("guidance_cache", "/c"))
        later = _FakeHandle(_target("assurance_sqlcipher", "/a"))
        steps = (
            _FakeStep("s1", "guidance_cache", findings=[_finding("s1")], fail_with=RuntimeError("boom")),
            _FakeStep("s2", "assurance_sqlcipher", findings=[_finding("s2")]),
        )
        reports, failed = apply_targets((failing, later), _registry(*steps))
        assert failed == failing.target.stable_id
        by_kind = {r.target.kind: r for r in reports}
        assert by_kind["assurance_sqlcipher"].detail is not None
        assert "re-run to resume" in by_kind["assurance_sqlcipher"].detail
        assert not later.uow.committed

    def test_manual_findings_are_skipped_and_leave_the_target_pending(self) -> None:
        handle = _FakeHandle(_target("guidance_cache", "/c"))
        step = _FakeStep("s1", "guidance_cache", findings=[_finding("s1", auto=False)])
        reports, failed = apply_targets((handle,), _registry(step))
        assert failed is None
        assert reports[0].state == "pending"
        assert not reports[0].committed
