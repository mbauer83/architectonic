"""`arch-update --commit`, `--resume`, `--rollback` and `--status`: the journaled half, composed.

The installed version runs the phases up to the handover and then *becomes* the new version by
executing the recorded resume command — the pid, and with it the lock, survive the `execv`. The new
version runs the rest. A failure anywhere rolls back from the journal, in either process, and the
exit status follows `arch-repair upgrade`'s table so an operator learns one.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from src.application.software_update.apply import PhaseFailed, run_phases
from src.application.software_update.evaluate import ReleaseCheck
from src.application.software_update.installation import InstallationObservation
from src.application.software_update.journal import (
    HANDOVER_PHASE,
    JOURNAL_FORMAT,
    JournalInvalid,
    PreviousState,
    TargetRelease,
    UpdateJournal,
    UpdatePhase,
)
from src.application.software_update.outcome import EXIT_BY_OUTCOME, UpdateOutcome, classify_outcome
from src.application.software_update.plan import UpdatePlan
from src.application.software_update.ports import UpdateActions
from src.application.software_update.release import sha256_of
from src.application.software_update.rollback import RollbackResult, roll_back
from src.domain.clock import utc_now_iso
from src.infrastructure.cli._update_report import render_journal_json, render_outcome_human, render_outcome_json
from src.infrastructure.software_update._commands import checkout_tool
from src.infrastructure.software_update.compose import ComposeActions, ComposeProject
from src.infrastructure.software_update.credentials import CredentialsUnavailable, answer_questions
from src.infrastructure.software_update.journal_store import FileJournalStore, UpdateInProgress
from src.infrastructure.software_update.local_actions import LocalCheckoutActions
from src.infrastructure.software_update.observation import deployment_identity_arguments

EXIT_USAGE = 2
ASSETS_DIR = "assets"


def commit(
    check: ReleaseCheck,
    observation: InstallationObservation,
    plan: UpdatePlan,
    *,
    root: Path,
    json_output: bool,
    resolve_selection: Sequence[str],
    compose_file: Path | None = None,
    uv: str = "uv",
) -> int:
    """Phases 1–4 as the installed version, then hand over to the new one."""
    assert check.release is not None
    store = FileJournalStore(root)
    try:
        store.acquire()
        if store.read() is not None:
            _say("an update is already in flight here; `arch-update --status`, then `--resume` or `--rollback`")
            return EXIT_BY_OUTCOME["infrastructure_failure"]
        answered = answer_questions(plan.questions, root, interactive=observation.interactive)
    except (UpdateInProgress, CredentialsUnavailable) as exc:
        _say(str(exc))
        return EXIT_BY_OUTCOME["infrastructure_failure"]
    for name in answered:
        _say(f"credential held for the restart: {name}")

    bundle_name = check.release.gui_bundle_name if plan.gui == "from_release" else None
    bundle = check.assets.get(bundle_name) if bundle_name else None
    if bundle is not None:
        assets = store.directory / ASSETS_DIR
        assets.mkdir(parents=True, exist_ok=True)
        (assets / str(bundle_name)).write_bytes(bundle)
    journal = UpdateJournal(
        format=JOURNAL_FORMAT,
        started_at=utc_now_iso(),
        previous=PreviousState(
            version=str(observation.software.version), commit=observation.software.commit,
            branch=observation.software.branch, backend=observation.backend,
            store_held_open=observation.store.held_open,
        ),
        target=TargetRelease(
            str(check.release.version), check.release.tag, check.release.commit, bundle_name,
            sha256_of(bundle) if bundle is not None else None,
        ),
        selection=observation.selection,
        checkout_move=plan.checkout_move,
        gui=plan.gui,
        phase="planned",
        resume_command=_resume_command(
            uv, root, json_output=json_output, resolve_selection=resolve_selection, compose_file=compose_file,
        ),
        notes=plan.notes,
        deployment=observation.kind,
        compose_file=None if compose_file is None else str(compose_file),
    )
    store.write(journal)
    actions = _actions(root, store, resolve_selection, uv, journal)
    try:
        journal = run_phases(journal, actions, store, through=HANDOVER_PHASE, on_phase=_announce)
    except PhaseFailed as failure:
        return _fail(failure, actions, store, json_output=json_output)
    _say(f"handing over to {journal.target.version}: {' '.join(journal.resume_command)}")
    return _hand_over(journal, actions, store, json_output=json_output)


def resume(root: Path, *, json_output: bool, resolve_selection: Sequence[str] = (), uv: str = "uv") -> int:
    """Phases 5–10 as the new version; refused when no handed-over journal is in flight."""
    store = FileJournalStore(root)
    try:
        store.acquire()
        journal = store.read()
    except (UpdateInProgress, JournalInvalid) as exc:
        _say(str(exc))
        return EXIT_BY_OUTCOME["infrastructure_failure"]
    if journal is None or not journal.handed_over:
        _say("nothing to resume: no update has been handed over in this checkout")
        return EXIT_USAGE
    actions = _actions(root, store, resolve_selection, uv, journal)
    try:
        journal = run_phases(journal, actions, store, through="verified", on_phase=_announce)
    except PhaseFailed as failure:
        return _fail(failure, actions, store, json_output=json_output)
    from src.infrastructure.software_update.gui_bundle import discard_previous  # noqa: PLC0415

    discard_previous(root)
    return _finish(journal, "updated", store, json_output=json_output, failure=None)


def rollback(root: Path, *, json_output: bool, uv: str = "uv") -> int:
    store = FileJournalStore(root)
    try:
        store.acquire()
        journal = store.read()
    except (UpdateInProgress, JournalInvalid) as exc:
        _say(str(exc))
        return EXIT_BY_OUTCOME["infrastructure_failure"]
    if journal is None:
        _say("nothing to roll back: no update is in flight in this checkout")
        return EXIT_USAGE
    result = roll_back(journal, _actions(root, store, (), uv, journal), store)
    outcome = classify_outcome(journal, failed=True, rolled_back=result.complete)
    return _finish(journal, outcome, store, json_output=json_output, failure="rolled back on request", result=result)


def status(root: Path, *, json_output: bool) -> int:
    store = FileJournalStore(root)
    try:
        journal = store.read()
    except JournalInvalid as exc:
        _say(str(exc))
        return EXIT_BY_OUTCOME["infrastructure_failure"]
    if journal is not None:
        print(render_journal_json(journal) if json_output else _in_flight_lines(journal))
        return 0
    archived = store.last_archived()
    if archived is None:
        print("{}" if json_output else "no update in flight, none recorded")
        return 0
    print(json.dumps(archived, indent=2) if json_output else _archived_line(archived))
    return 0


def _in_flight_lines(journal: UpdateJournal) -> str:
    state = "handed over to the new version" if journal.handed_over else "running as the installed version"
    in_flight = f" ({journal.in_flight} in flight)" if journal.in_flight else ""
    return (
        f"in flight   {journal.previous.version} → {journal.target.version}, {state}\n"
        f"phase       {journal.phase}{in_flight}\n"
        "            `arch-update --resume` continues it; `arch-update --rollback` puts it back"
    )


def _archived_line(archived: dict[str, object]) -> str:
    target, previous = archived.get("target"), archived.get("previous")
    target_version = target.get("version") if isinstance(target, dict) else None
    previous_version = previous.get("version") if isinstance(previous, dict) else None
    return (
        f"last update {previous_version} → {target_version}: {archived.get('outcome')} "
        f"(started {archived.get('started_at')})"
    )


def _hand_over(
    journal: UpdateJournal, actions: UpdateActions, store: FileJournalStore, *, json_output: bool,
) -> int:
    executable = shutil.which(journal.resume_command[0]) or journal.resume_command[0]
    sys.stdout.flush()
    sys.stderr.flush()
    # `uv run` starts the tool as a child, so the pid this lock names would outlive the handover as
    # uv itself, and the resumed version would find its own update "already running". The journal,
    # not the lock, is what keeps a second `--commit` out while an update is in flight.
    store.release()
    try:
        os.execv(executable, journal.resume_command)
    except OSError as exc:
        failure = PhaseFailed(
            journal.begin("gui_installed"), "gui_installed", f"could not re-execute as the new version: {exc}",
        )
        return _fail(failure, actions, store, json_output=json_output)
    raise AssertionError("execv returned")  # pragma: no cover


def _fail(failure: PhaseFailed, actions: UpdateActions, store: FileJournalStore, *, json_output: bool) -> int:
    _say(f"phase {failure.phase} failed: {failure.error}")
    _say("rolling back")
    result = roll_back(failure.journal, actions, store)
    outcome = classify_outcome(failure.journal, failed=True, rolled_back=result.complete)
    return _finish(failure.journal, outcome, store, json_output=json_output, failure=str(failure), result=result)


def _finish(
    journal: UpdateJournal,
    outcome: UpdateOutcome,
    store: FileJournalStore,
    *,
    json_output: bool,
    failure: str | None,
    result: RollbackResult | None = None,
) -> int:
    restored = result.restored if result else ()
    remaining = result.remaining if result else ()
    store.archive(journal, outcome)
    shutil.rmtree(store.directory / ASSETS_DIR, ignore_errors=True)
    store.release()
    render = render_outcome_json if json_output else render_outcome_human
    print(render(journal, outcome, failure=failure, restored=restored, remaining=remaining))
    return EXIT_BY_OUTCOME[outcome]


def _actions(
    root: Path, store: FileJournalStore, resolve_selection: Sequence[str], uv: str, journal: UpdateJournal,
) -> UpdateActions:
    if journal.deployment == "compose-host":
        compose_file = Path(journal.compose_file) if journal.compose_file else None
        project = ComposeProject(root, compose_file=compose_file)
        return ComposeActions(
            root, project, installed_version=journal.previous.version, resolve_selection=resolve_selection, uv=uv,
        )
    return LocalCheckoutActions(
        root, assets_dir=store.directory / ASSETS_DIR, deployment_arguments=deployment_identity_arguments(root),
        resolve_selection=resolve_selection, uv=uv,
    )


def _resume_command(
    uv: str, root: Path, *, json_output: bool, resolve_selection: Sequence[str], compose_file: Path | None,
) -> tuple[str, ...]:
    command = checkout_tool(uv, root, "arch-update", "--resume")
    if json_output:
        command.append("--json")
    for slug in resolve_selection:
        command += ["--resolve-selection", slug]
    if compose_file is not None:
        command += ["--compose-file", str(compose_file)]
    return tuple(command)


def _announce(phase: UpdatePhase) -> None:
    _say(f"phase: {phase.replace('_', ' ')} …")


def _say(text: str) -> None:
    print(text, file=sys.stderr)
