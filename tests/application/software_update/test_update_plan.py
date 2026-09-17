"""Every state an installation can be in reaches the planner as a value, and each row of the refusal table holds."""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.application.software_update.installation import (
    BackendObservation,
    DependencySelection,
    InstallationObservation,
    InstalledSoftware,
    StoreObservation,
    Tooling,
)
from src.application.software_update.plan import (
    RehearsalVerdict,
    ReleaseVerification,
    UpdatePlan,
    UpdateRefused,
    UpToDate,
    plan_update,
)
from src.application.software_update.release import AssetVerification, PublishedRelease, ReleaseAsset
from src.application.software_update.version import ReleaseVersion

INSTALLED = InstalledSoftware(ReleaseVersion(0, 10, 0), "abc123", "main", (), True, "stamp", "1.2026.3")
RELEASE = PublishedRelease(
    ReleaseVersion(0, 10, 1), "v0.10.1", "def456", "2026-10-02", False,
    (ReleaseAsset("architectonic-gui-0.10.1.tar.gz", "https://x/a", "sha256:" + "a" * 64, 10),),
)
BUNDLE_OK = AssetVerification("architectonic-gui-0.10.1.tar.gz", "verified", "a" * 64, ("release",))
GOOD = ReleaseVerification(True, "verified", (BUNDLE_OK,), "verified")
BUNDLE_BAD = AssetVerification("a", "digest_mismatch", "b" * 64, ("release",), "the bytes do not match")
IF, BLOCKED = "infrastructure_failure", "blocked"
STOPPED = BackendObservation(False, None, None, None, ())
FOREGROUND = BackendObservation(True, 1, 8000, False, ())
WEDGED = BackendObservation(False, 1, 8000, None, (), unhealthy=True)
DIRTY = replace(INSTALLED, modified_tracked=("src/x.py",))
BLOCKING = RehearsalVerdict(1, 0, 0, ("selection-divergent",), (), ())
UNINSPECTABLE = RehearsalVerdict(1, 1, 0, (), ("assurance_sqlcipher",), ())
CLEAR = RehearsalVerdict(2, 3, 3, (), (), ())


def _observation(**over: object) -> InstallationObservation:
    base = InstallationObservation(
        kind="local-checkout", software=INSTALLED, selection=DependencySelection(("gui",), ()),
        backend=BackendObservation(True, 4242, 8000, True, ()),
        store=StoreObservation(True, True, "manual", True),
        remotes_needing_credentials=(), tooling=Tooling(True, True, False, False), interactive=True,
    )
    return replace(base, **over)  # type: ignore[arg-type]


def test_the_ordinary_case_plans_every_step_in_order() -> None:
    plan = plan_update(_observation(), RELEASE, GOOD, CLEAR)

    assert isinstance(plan, UpdatePlan)
    assert [step.key for step in plan.steps] == [
        "stop_backend", "move_checkout", "sync_environment", "provision_gui", "reconcile_assets",
        "migrate", "start_backend", "authorize_store", "verify",
    ]
    assert plan.gui == "from_release" and plan.checkout_move == "fast_forward"
    assert plan.questions == ()


def test_an_installed_version_at_or_past_the_release_is_up_to_date() -> None:
    same = replace(RELEASE, version=ReleaseVersion(0, 10, 0))
    older = replace(RELEASE, version=ReleaseVersion(0, 9, 9))
    assert isinstance(plan_update(_observation(), same, GOOD, CLEAR), UpToDate)
    assert isinstance(plan_update(_observation(), older, GOOD, CLEAR), UpToDate)


def test_a_stopped_backend_is_left_stopped_and_no_store_is_touched() -> None:
    plan = plan_update(
        _observation(backend=STOPPED, store=StoreObservation(True, False, "manual", True)),
        RELEASE, GOOD, CLEAR,
    )
    assert isinstance(plan, UpdatePlan)
    assert "stop_backend" not in [s.key for s in plan.steps] and "start_backend" not in [s.key for s in plan.steps]
    assert not plan.authorize_store and plan.questions == ()


def test_a_persistent_store_needs_no_authorization_step() -> None:
    plan = plan_update(_observation(store=StoreObservation(True, True, "persistent", True)), RELEASE, GOOD, CLEAR)
    assert isinstance(plan, UpdatePlan) and not plan.authorize_store


def test_the_gui_strategy_follows_what_the_release_carries_and_what_the_box_has() -> None:
    bare = replace(RELEASE, assets=())
    verification = replace(GOOD, assets=())
    with_npm = plan_update(_observation(), bare, verification, CLEAR)
    without_npm = plan_update(_observation(tooling=Tooling(True, False, False, False)), bare, verification, CLEAR)
    assert isinstance(with_npm, UpdatePlan) and with_npm.gui == "build_locally"
    assert isinstance(without_npm, UpdatePlan) and without_npm.gui == "leave_stale"
    assert any("lag" in note for note in without_npm.notes)


@pytest.mark.verifies("REQ@1789640735.7Qke86l")
def test_the_questions_name_what_the_restart_will_need() -> None:
    plan = plan_update(
        _observation(
            remotes_needing_credentials=("enterprise-repository",),
            store=StoreObservation(True, True, "manual", False, "ARCH_ASSURANCE_MASTER_PASSWORD"),
        ),
        RELEASE, GOOD, CLEAR,
    )
    assert isinstance(plan, UpdatePlan)
    assert [q.what for q in plan.questions] == ["git credentials", "assurance vault master password"]


@pytest.mark.parametrize(
    ("observation", "release", "verification", "rehearsal", "outcome", "fragment"),
    [
        (_observation(kind="container"), RELEASE, GOOD, CLEAR, IF, "on the host"),
        (_observation(kind="remote-attached"), RELEASE, GOOD, CLEAR, IF, "ARCH_MCP_BACKEND_URL"),
        (_observation(kind="ambiguous"), RELEASE, GOOD, CLEAR, BLOCKED, "--deployment"),
        (_observation(tooling=Tooling(False, True, False, False)), RELEASE, GOOD, CLEAR, IF, "uv"),
        (_observation(), RELEASE, replace(GOOD, commit_matches=False), CLEAR, IF, "does not name the commit"),
        (_observation(), RELEASE, replace(GOOD, signature="unsigned"), CLEAR, IF, "release-signers"),
        (_observation(), RELEASE, replace(GOOD, signature="untrusted"), CLEAR, IF, "release-signers"),
        (_observation(), RELEASE, replace(GOOD, assets=(BUNDLE_BAD,)), CLEAR, IF, "do not match"),
        (_observation(software=DIRTY), RELEASE, GOOD, CLEAR, BLOCKED, "src/x.py"),
        (_observation(backend=FOREGROUND), RELEASE, GOOD, CLEAR, BLOCKED, "foreground"),
        (_observation(backend=WEDGED), RELEASE, GOOD, CLEAR, BLOCKED, "--stop"),
        (_observation(), RELEASE, GOOD, BLOCKING, BLOCKED, "selection"),
        (_observation(), RELEASE, GOOD, UNINSPECTABLE, BLOCKED, "sqlcipher"),
        (
            _observation(interactive=False, remotes_needing_credentials=("enterprise-repository",)),
            RELEASE, GOOD, CLEAR, IF, "ARCH_GIT",
        ),
    ],
    ids=[
        "container", "remote-attached", "ambiguous", "no-uv", "commit-mismatch", "unsigned", "untrusted",
        "asset-mismatch", "dirty-checkout", "foreground-backend", "wedged-backend", "rehearsal-blocking",
        "rehearsal-uninspectable", "credential-without-tty",
    ],
)
@pytest.mark.verifies("REQ@1789640735.7Qke86l")
def test_each_row_of_the_refusal_table(observation, release, verification, rehearsal, outcome, fragment) -> None:  # noqa: ANN001
    refused = plan_update(observation, release, verification, rehearsal)

    assert isinstance(refused, UpdateRefused), refused
    assert refused.outcome == outcome
    assert fragment in refused.reason + refused.remedy


def test_an_unsigned_tag_is_only_a_note_where_no_signers_file_is_installed() -> None:
    plan = plan_update(
        _observation(software=replace(INSTALLED, signers_file_present=False)),
        RELEASE, replace(GOOD, signature="not_enforced"), CLEAR,
    )
    assert isinstance(plan, UpdatePlan)
    assert any("not enforced" in note for note in plan.notes)


def test_a_credential_question_is_asked_rather_than_refused_when_there_is_a_terminal() -> None:
    plan = plan_update(_observation(remotes_needing_credentials=("enterprise-repository",)), RELEASE, GOOD, CLEAR)
    assert isinstance(plan, UpdatePlan) and len(plan.questions) == 1


def test_a_compose_host_is_planned_in_the_container_driver_s_order_with_nothing_prompted() -> None:
    observation = _observation(
        kind="compose-host", backend=BackendObservation(True, None, 8000, True, ()),
        remotes_needing_credentials=("enterprise",), interactive=False,
    )

    plan = plan_update(observation, RELEASE, GOOD, CLEAR)

    assert isinstance(plan, UpdatePlan) and plan.gui == "in_image" and plan.questions == ()
    assert [step.key for step in plan.steps] == [
        "move_checkout", "sync_environment", "stop_backend", "migrate", "start_backend", "verify",
    ]
    assert "docker compose build" in plan.steps[1].description
