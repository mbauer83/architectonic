"""Shared repository-upgrade step-conformance contract.

Every `UpgradeStep`'s safety argument for "an uncommitted local edit is carried forward,
never lost" rests on one property: `apply()` rewrites narrowly and leaves content it has no
opinion about byte-for-byte intact. That's a per-step promise, not something the framework
enforces structurally — this helper turns it into something every step's own test module can
assert directly, rather than trusting it silently.

Usage: set up a fixture file under the view/writer's repo root containing both (a) an
instance of the step's detectable legacy pattern and (b) `unknown_marker` embedded somewhere
in that same file (e.g. an extra YAML key, or an extra body line) — content a naive
reconstruct-from-scratch step would drop. Then call `assert_step_preserves_unknown_content`.
"""

from __future__ import annotations

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter, UpgradeStep


def assert_step_preserves_unknown_content(
    step: UpgradeStep,
    view: RepoUpgradeView,
    writer: RepoUpgradeWriter,
    *,
    location: str,
    unknown_marker: str,
) -> None:
    before = view.read_text(location) or ""
    assert unknown_marker in before, (
        "test setup error: unknown_marker must already be present in the fixture at "
        f"{location!r} before calling apply()"
    )

    findings = step.detect(view)
    assert findings, f"step {step.id!r} detected nothing in {location!r} — fixture doesn't match its pattern"

    auto_findings = [f for f in findings if f.auto_migratable]
    assert auto_findings, (
        f"step {step.id!r} produced only manual (auto_migratable=False) findings for "
        f"{location!r} — this conformance check only applies to steps that actually rewrite "
        "content; an always-manual step has nothing to prove here"
    )

    step.apply(view, writer, auto_findings)

    after = view.read_text(location) or ""
    assert unknown_marker in after, (
        f"step {step.id!r} dropped unrelated content in {location!r} during apply() — an "
        "uncommitted edit or a field this step doesn't recognize would be silently lost, "
        "violating the repository-upgrade step-conformance obligation"
    )
