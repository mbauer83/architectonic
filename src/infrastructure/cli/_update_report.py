"""What `arch-update` prints: the human form of the check and the plan, and the same object as JSON.

Presentation only, kept apart from the command the way `_lifecycle_cli` is kept apart from
`backend_control`: the check decides, this says. stdout carries the report and nothing else, so
`--json` is the same object the human form renders and diagnostics go to stderr.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from src.application.software_update.evaluate import ReleaseCheck
from src.application.software_update.journal import UpdateJournal
from src.application.software_update.outcome import EXIT_BY_OUTCOME, UpdateOutcome
from src.application.software_update.plan import (
    PlanningResult,
    RehearsalVerdict,
    UpdatePlan,
    UpdateRefused,
    UpToDate,
)
from src.application.software_update.release import AssetVerification

UPDATE_REPORT_SCHEMA_VERSION = "1"


def report_mapping(
    check: ReleaseCheck, planning: PlanningResult | None, *, rehearsal: RehearsalVerdict | None = None,
) -> dict[str, object]:
    installed = check.installed
    release = check.release
    payload: dict[str, object] = {
        "report_schema_version": UPDATE_REPORT_SCHEMA_VERSION,
        "installed": {
            "version": str(installed.version) if installed.version else None,
            "commit": installed.commit,
            "branch": installed.branch,
            "clean": installed.clean,
            "modified_tracked": list(installed.modified_tracked),
            "signers_file_present": installed.signers_file_present,
            "gui_stamp": installed.gui_stamp,
        },
        "release": None if release is None else {
            "version": str(release.version),
            "tag": release.tag,
            "commit": release.commit,
            "published_at": release.published_at,
            "prerelease": release.prerelease,
            "assets": [asdict(asset) for asset in release.assets],
        },
        "update_available": check.update_available,
        "verification": None if check.verification is None else {
            "fetched_commit": check.fetched_commit,
            "commit_matches": check.verification.commit_matches,
            "signature": check.verification.signature,
            "assets": [asdict(item) for item in check.verification.assets],
            "provenance": check.verification.provenance,
        },
        "rehearsal": None if rehearsal is None else asdict(rehearsal),
        "plan": None,
        "refused": None,
    }
    if isinstance(planning, UpdatePlan):
        payload["plan"] = {
            "target": str(planning.target),
            "checkout_move": planning.checkout_move,
            "gui": planning.gui,
            "steps": [asdict(step) for step in planning.steps],
            "will_ask_for": [asdict(question) for question in planning.questions],
            "notes": list(planning.notes),
        }
    elif isinstance(planning, UpdateRefused):
        payload["refused"] = asdict(planning)
    return payload


def render_json(
    check: ReleaseCheck, planning: PlanningResult | None, *, rehearsal: RehearsalVerdict | None = None,
) -> str:
    return json.dumps(report_mapping(check, planning, rehearsal=rehearsal), indent=2, sort_keys=False)


def render_human(
    check: ReleaseCheck,
    planning: PlanningResult | None,
    *,
    situation: str,
    rehearsal: RehearsalVerdict | None = None,
) -> str:
    lines = [f"installed   {_installed_line(check, situation)}"]
    release = check.release
    if release is None:
        lines.append("release     none published")
        return "\n".join(lines)
    lines.append(f"release     {_release_line(check)}")
    if check.verification is not None:
        for item in check.verification.assets:
            lines.append(f"assets      {item.asset}   {_asset_verdict(item)}")
        if not check.verification.assets:
            lines.append("assets      the release carries no GUI bundle")
        lines.append(f"provenance  {check.verification.provenance.replace('_', ' ')}")
    if rehearsal is not None:
        lines.append(f"rehearsal   {_rehearsal_line(check, rehearsal)}")
    if isinstance(planning, UpToDate):
        lines.append(f"status      up to date ({planning.installed} is the newest release)")
    elif isinstance(planning, UpdateRefused):
        lines.append(f"refused     {planning.reason}")
        lines.append(f"            → {planning.remedy}")
    elif isinstance(planning, UpdatePlan):
        for index, step in enumerate(planning.steps, start=1):
            label = "plan        " if index == 1 else "            "
            lines.append(f"{label}{index} {step.description}")
        for question in planning.questions:
            lines.append(f"will ask for  {question.what} ({question.why}); or set {question.env_name}")
        for note in planning.notes:
            lines.append(f"notes       {note}")
    return "\n".join(lines)


def _installed_line(check: ReleaseCheck, situation: str) -> str:
    installed = check.installed
    version = str(installed.version) if installed.version else "unknown version"
    branch = installed.branch or "detached"
    clean = "clean" if installed.clean else f"{len(installed.modified_tracked)} modified tracked file(s)"
    return f"{version}   {situation} · {branch} @ {installed.commit[:7]} · {clean}"


def _release_line(check: ReleaseCheck) -> str:
    release = check.release
    assert release is not None
    parts = [
        str(release.version),
        f"published {release.published_at[:10] or 'unknown'}",
        f"tag {release.tag} → {release.commit[:7]}",
    ]
    if release.prerelease:
        parts.append("pre-release")
    verification = check.verification
    if verification is not None:
        parts.append(f"signature: {verification.signature.replace('_', ' ')}")
        matches = verification.commit_matches
        parts.append("commit matches the release" if matches else "COMMIT DOES NOT MATCH THE RELEASE")
    return " · ".join(parts)


def _rehearsal_line(check: ReleaseCheck, rehearsal: RehearsalVerdict) -> str:
    assert check.release is not None
    if rehearsal.could_not_run:
        return f"arch-repair upgrade {check.release.version} could not be run: {rehearsal.errors[0]}"
    counts = (
        f"arch-repair upgrade {check.release.version} · {rehearsal.repositories} repositories, "
        f"{rehearsal.operational_targets} operational targets · {rehearsal.auto_migratable} auto-migratable, "
        f"{len(rehearsal.blocking)} blocking, {len(rehearsal.uninspectable)} uninspectable"
    )
    return counts if not rehearsal.errors else f"{counts}, {len(rehearsal.errors)} step error(s)"


def _asset_verdict(item: AssetVerification) -> str:
    if item.ok:
        return "digest ok (" + ", ".join(item.checked_against) + ")"
    return f"{item.verdict.replace('_', ' ').upper()}: {item.detail}"


def outcome_mapping(
    journal: UpdateJournal,
    outcome: UpdateOutcome,
    *,
    failure: str | None,
    restored: tuple[str, ...] = (),
    remaining: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "report_schema_version": UPDATE_REPORT_SCHEMA_VERSION,
        "outcome": outcome,
        "exit_status": EXIT_BY_OUTCOME[outcome],
        "previous": {"version": journal.previous.version, "commit": journal.previous.commit},
        "target": {"version": journal.target.version, "tag": journal.target.tag, "commit": journal.target.commit},
        "phase": journal.phase,
        "in_flight": journal.in_flight,
        "checkpoint_set": journal.checkpoint_set,
        "migration_committed": journal.migration_committed,
        "failure": failure,
        "rollback": None if not (restored or remaining) else {"restored": list(restored), "remaining": list(remaining)},
        "notes": list(journal.notes),
    }


def render_journal_json(journal: UpdateJournal) -> str:
    """An update in flight, as `--status --json` reports it: the journal itself, with its schema."""
    return json.dumps({"report_schema_version": UPDATE_REPORT_SCHEMA_VERSION, **journal.to_mapping()}, indent=2)


def render_outcome_json(
    journal: UpdateJournal,
    outcome: UpdateOutcome,
    *,
    failure: str | None,
    restored: tuple[str, ...] = (),
    remaining: tuple[str, ...] = (),
) -> str:
    return json.dumps(
        outcome_mapping(journal, outcome, failure=failure, restored=restored, remaining=remaining), indent=2,
    )


def render_outcome_human(
    journal: UpdateJournal,
    outcome: UpdateOutcome,
    *,
    failure: str | None,
    restored: tuple[str, ...] = (),
    remaining: tuple[str, ...] = (),
) -> str:
    previous, target = journal.previous, journal.target
    headline = {
        "updated": f"updated     {previous.version} → {target.version} ({target.tag} @ {target.commit[:7]}), verified",
        "blocked": f"blocked     {target.version} was not installed; still at {previous.version}, as before",
        "partial": f"partial     the update to {target.version} failed and could not be fully put back",
        "infrastructure_failure": f"failed      before anything changed; the installation is at {previous.version}",
        "up_to_date": f"up to date  {previous.version}",
    }[outcome]
    lines = [headline]
    if failure:
        lines.append(f"failure     {failure}")
    for item in restored:
        lines.append(f"restored    {item}")
    for item in remaining:
        lines.append(f"REMAINING   {item}")
    if journal.checkpoint_set:
        lines.append(f"safety      arch-repair upgrade --restore {journal.checkpoint_set} (one set is kept)")
    for note in journal.notes:
        lines.append(f"notes       {note}")
    return "\n".join(lines)
