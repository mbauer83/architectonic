"""A store written before renames cascaded names architecture artifacts by former titles.

The reference resolves — identity is the stem — so nothing in the product notices, and the reader of
a safety argument sees a name the artifact dropped. These cover the respelling, the two ways it must
decline (no repository to ask, or two candidate spellings), and the one shape that could lose data:
a node already holding the current spelling for the same ref type, whose row is a primary-key
collision waiting to happen.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.application.deployment_upgrade.steps.assurance_arch_ref_respell import (
    AssuranceArchRefRespellStep,
)
from src.domain.artifact_id import canonical_ids_by_stem
from src.domain.repository.operational_upgrade import UpgradeTarget
from src.infrastructure.deployment.database_targets import DatabaseTargetHandle

STEM = "GOL@1000000001.aBcDeF1"
CURRENT = f"{STEM}.current-title"
FORMER = f"{STEM}.the-title-it-had"

_SCHEMA = """
CREATE TABLE arch_refs (
    assurance_node_id TEXT NOT NULL,
    arch_artifact_id  TEXT NOT NULL,
    ref_type          TEXT NOT NULL,
    resolved_at       TEXT,
    PRIMARY KEY (assurance_node_id, arch_artifact_id, ref_type)
);
"""


def _handle(tmp_path: Path, rows: list[tuple[str, str, str, str | None]]) -> DatabaseTargetHandle:
    path = tmp_path / "assurance.db"
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.executemany("INSERT INTO arch_refs VALUES (?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(path, isolation_level=None)

    return DatabaseTargetHandle(
        target=UpgradeTarget(
            kind="assurance_sqlcipher",
            stable_id=f"assurance_sqlcipher:{path}",
            display_location=str(path),
            current_version=None,
            credential_requirement="sqlcipher_key",
        ),
        connect=connect,
        inspectable=True,
    )


def _refs(handle: DatabaseTargetHandle) -> list[tuple[str, str, str]]:
    conn = handle.connect()
    try:
        return sorted(
            (str(a), str(b), str(c))
            for a, b, c in conn.execute(
                "SELECT assurance_node_id, arch_artifact_id, ref_type FROM arch_refs"
            ).fetchall()
        )
    finally:
        conn.close()


def _step(*spellings: str) -> AssuranceArchRefRespellStep:
    return AssuranceArchRefRespellStep(canonical_ids_by_stem(spellings))


def _run(step: AssuranceArchRefRespellStep, handle: DatabaseTargetHandle) -> None:
    view = handle.view()
    uow = handle.begin()
    step.apply(view, uow, step.detect(view))
    uow.commit()


class TestAFormerTitleIsRespelled:
    def test_it_is_detected(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [("HAZ@1.a.h", FORMER, "mitigated-by", None)])

        findings = _step(CURRENT).detect(handle.view())

        assert len(findings) == 1
        assert findings[0].auto_migratable
        assert FORMER in findings[0].rewrite_summary

    def test_the_row_moves_to_the_current_spelling(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [("HAZ@1.a.h", FORMER, "mitigated-by", None)])

        _run(_step(CURRENT), handle)

        assert _refs(handle) == [("HAZ@1.a.h", CURRENT, "mitigated-by")]

    def test_a_second_run_finds_nothing(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [("HAZ@1.a.h", FORMER, "mitigated-by", None)])
        _run(_step(CURRENT), handle)

        assert _step(CURRENT).detect(handle.view()) == []

    def test_a_node_already_holding_the_current_spelling_keeps_one_row(self, tmp_path: Path) -> None:
        """The collision case: both spellings on one node and ref type are the same reference, and
        the update would violate the primary key. The current row survives with its resolution."""
        handle = _handle(
            tmp_path,
            [
                ("HAZ@1.a.h", FORMER, "mitigated-by", None),
                ("HAZ@1.a.h", CURRENT, "mitigated-by", "2026-01-01T00:00:00Z"),
            ],
        )

        _run(_step(CURRENT), handle)

        assert _refs(handle) == [("HAZ@1.a.h", CURRENT, "mitigated-by")]
        conn = handle.connect()
        try:
            resolved = conn.execute("SELECT resolved_at FROM arch_refs").fetchone()[0]
        finally:
            conn.close()
        assert resolved == "2026-01-01T00:00:00Z", "the resolved row was the one dropped"


class TestWhenItMustDecline:
    def test_without_a_repository_index_it_migrates_nothing(self, tmp_path: Path) -> None:
        """A deployment-only run has nothing to ask how an artifact is spelled now."""
        handle = _handle(tmp_path, [("HAZ@1.a.h", FORMER, "mitigated-by", None)])

        assert AssuranceArchRefRespellStep().detect(handle.view()) == []

    def test_two_candidate_spellings_leave_the_reference_alone(self, tmp_path: Path) -> None:
        """Engagement and enterprise can both hold the stem; respelling to a guess would retitle a
        reference that may already be the correct one of the two."""
        handle = _handle(tmp_path, [("HAZ@1.a.h", FORMER, "mitigated-by", None)])

        assert _step(CURRENT, f"{STEM}.enterprise-title").detect(handle.view()) == []

    def test_a_current_reference_is_not_a_finding(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [("HAZ@1.a.h", CURRENT, "mitigated-by", None)])

        assert _step(CURRENT).detect(handle.view()) == []
