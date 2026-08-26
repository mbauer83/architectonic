"""E319: two artifacts sharing one rename-stable id.

Identity is the ``PREFIX@epoch.random`` stem. Two files carrying the same stem are two artifacts
claiming one identity, and every reference spelled with that stem resolves to whichever the index
happened to key — silently, and differently after a reindex.

**The condition was already fail-closed, in one place only.** `assert_no_duplicate_short_ids` aborts
backend startup over exactly this, so a repository holding one cannot be served. It says nothing to an
author working through MCP, who never restarts anything: a rename that left the old file behind ran
for a day with `artifact_verify` reporting 0 errors and 0 warnings the whole time, while the backend
would have refused to start on the same content. A condition serious enough to stop the process is not
one the verifier should be silent about.

An error rather than a warning, and this one does not have the usual reason to soften. The other
recent diagnostics describe content authored in good faith that still renders; this describes two
files that cannot both be right, where the product's own startup already refuses to proceed. Making it
a warning here would mean the verifier and the backend disagree about whether the repository is
usable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.application.verification._duplicate_identity_rules import (
    DuplicateStableIdContribution,
)
from src.domain.ontology_representation.artifact_types import EntityRecord


class _Result:
    def __init__(self) -> None:
        self.issues: list[Any] = []


def _entity(artifact_id: str, name: str, host_diagram_id: str | None = None) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="application-component",
        name=name,
        version="0.1.0",
        status="active",
        domain="application",
        subdomain="",
        path=Path(f"{artifact_id}.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=name,
        display_alias="APP_x",
        specializations=(),
        attributes={},
        host_diagram_id=host_diagram_id,
    )


class _Candidate:
    def __init__(self, entities: list[EntityRecord]) -> None:
        self._entities = entities

    def list_entities(self, **kwargs: object) -> list[EntityRecord]:
        del kwargs
        return list(self._entities)

    def list_diagrams(self, **kwargs: object) -> list[object]:
        del kwargs
        return []


class _Ctx:
    def __init__(self, entities: list[EntityRecord]) -> None:
        self.candidate = _Candidate(entities)
        self.committed = self.candidate
        self.location = "repo"
        self.catalogs = object()
        self.type_references_blocking = True


def _run(entities: list[EntityRecord]) -> list[Any]:
    result = _Result()
    DuplicateStableIdContribution().run(_Ctx(entities), result)
    return result.issues


_STEM = "APP@1787000000.aBcDeF"


class TestWhatIsReported:
    def test_two_files_sharing_one_stem_are_an_error(self) -> None:
        issues = _run([
            _entity(f"{_STEM}.planning-data-carries-its-own-lineage", "Planning Data"),
            _entity(f"{_STEM}.manufacturing-planning-runs-nightly", "Manufacturing Planning"),
        ])

        assert [issue.code for issue in issues] == ["E319"]
        assert issues[0].severity == "error"

    def test_both_spellings_are_named(self) -> None:
        """An author cannot act on "there is a duplicate": which two files, so one can be deleted."""
        issues = _run([
            _entity(f"{_STEM}.planning-data-carries-its-own-lineage", "Planning Data"),
            _entity(f"{_STEM}.manufacturing-planning-runs-nightly", "Manufacturing Planning"),
        ])

        assert "planning-data-carries-its-own-lineage" in issues[0].message
        assert "manufacturing-planning-runs-nightly" in issues[0].message

    def test_three_files_sharing_a_stem_are_one_finding_naming_all_three(self) -> None:
        """One finding per identity, not per pair: a reader is fixing one duplicated id."""
        issues = _run([
            _entity(f"{_STEM}.first", "First"),
            _entity(f"{_STEM}.second", "Second"),
            _entity(f"{_STEM}.third", "Third"),
        ])

        assert len(issues) == 1
        assert all(slug in issues[0].message for slug in ("first", "second", "third"))

    def test_two_distinct_identities_are_two_findings(self) -> None:
        other = "APP@1787000001.zZyYxX"
        issues = _run([
            _entity(f"{_STEM}.one", "One"), _entity(f"{_STEM}.two", "Two"),
            _entity(f"{other}.one", "One"), _entity(f"{other}.two", "Two"),
        ])

        assert len(issues) == 2


class TestWhatIsNotReported:
    def test_distinct_identities_report_nothing(self) -> None:
        issues = _run([
            _entity("APP@1787000000.aBcDeF.first", "First"),
            _entity("APP@1787000001.gHiJkL.second", "Second"),
        ])

        assert issues == []

    def test_one_artifact_listed_once_reports_nothing(self) -> None:
        assert _run([_entity(f"{_STEM}.only", "Only")]) == []

    def test_the_same_full_id_twice_is_not_two_files(self) -> None:
        """One artifact reached by two routes is not a duplicated identity — the overlay a candidate
        transaction builds can list a record the committed view also holds, and reporting that would
        make every write report itself."""
        same = f"{_STEM}.the-same-artifact"

        assert _run([_entity(same, "Same"), _entity(same, "Same")]) == []

    def test_an_empty_repository_reports_nothing(self) -> None:
        assert _run([]) == []

    def test_a_diagram_only_element_is_not_a_competing_file(self) -> None:
        """Its id is its diagram's own with a compartment appended, so it shares the stem by
        construction. Counting it made every diagram drawing one report itself as its own duplicate —
        which the existing suite caught, on a delete that had nothing to do with identity."""
        diagram = "DIA@1779000003.tshrt.to-delete"

        assert _run([
            _entity(diagram, "To Delete"),
            _entity(f"{diagram}#software-system/sys", "MySystem", host_diagram_id=diagram),
        ]) == []

    def test_two_diagram_only_elements_of_one_diagram_report_nothing(self) -> None:
        diagram = "DIA@1779000003.tshrt.to-delete"

        assert _run([
            _entity(f"{diagram}#software-system/one", "One", host_diagram_id=diagram),
            _entity(f"{diagram}#software-system/two", "Two", host_diagram_id=diagram),
        ]) == []


class TestItAgreesWithWhatTheBackendRefusesToServe:
    def test_the_condition_is_the_one_startup_aborts_on(self) -> None:
        """The backend already exits on this, so the verifier saying nothing meant a repository could
        verify clean and be unserveable. Stated as a property of the rule, not of a message: both ask
        whether one stem maps to more than one artifact."""
        from src.domain.artifact_id import stable_id  # noqa: PLC0415

        duplicated = [
            _entity(f"{_STEM}.planning-data-carries-its-own-lineage", "Planning Data"),
            _entity(f"{_STEM}.manufacturing-planning-runs-nightly", "Manufacturing Planning"),
        ]

        stems = {stable_id(e.artifact_id) for e in duplicated}

        assert len(stems) == 1
        assert _run(duplicated) != []


class TestItIsActuallyInvoked:
    def test_the_rule_is_registered_with_the_generic_contributions(self) -> None:
        """A contribution that answers correctly and is never invoked reports nothing, and from a unit
        test the two look identical. The registry is what the verifier iterates."""
        from src.application.verification import _verifier_contribution_runner  # noqa: F401, PLC0415
        from src.domain.diagrams.diagram_verification import (  # noqa: PLC0415
            get_generic_repository_contributions,
        )

        registered = {type(c) for c in get_generic_repository_contributions()}

        assert DuplicateStableIdContribution in registered

    def test_the_code_it_declares_is_the_one_it_emits(self) -> None:
        """A code emitted but not declared is one no surface can offer to filter on."""
        issues = _run([_entity(f"{_STEM}.one", "One"), _entity(f"{_STEM}.two", "Two")])

        assert {issue.code for issue in issues} <= set(DuplicateStableIdContribution.diagnostic_codes)


class TestItSurvivesAPassThatReusesStoredState:
    """A repository-level rule cannot be skipped because few files changed.

    Repository contributions ran only on the full pass. A rule asking whether two files claim one
    identity is not answered by any file's own state, so a pass reusing that state answered "clean"
    for a repository the backend refuses to serve — which is the shape of the incident: verification
    said 0 errors for a day. Documents were already verified on the incremental modes for exactly this
    reason, and the same guard now carries the repository rules.

    Through `artifact_verify`, because the property is about which rules a *pass* runs, and a unit
    test of the contribution cannot see a pass that never invokes it.
    """

    def test_a_duplicate_is_reported_by_a_later_pass_over_a_verified_repository(
        self, tmp_path: Path
    ) -> None:
        import asyncio  # noqa: PLC0415

        from src.infrastructure.mcp import mcp_artifact_server as mcp  # noqa: PLC0415
        from src.infrastructure.mcp.artifact_mcp.context import clear_caches_for_repo  # noqa: PLC0415

        repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        (repo / "model").mkdir(parents=True)
        (repo / "diagram-catalog" / "diagrams").mkdir(parents=True)
        created = mcp.artifact_create_entity(
            artifact_type="application-component", name="Planning Data", summary="s",
            dry_run=False, repo_root=str(repo),
        )
        real = str(created["artifact_id"])

        def codes(report: dict) -> set[str]:
            return {
                issue["code"]
                for entry in report.get("results", [])
                for issue in entry.get("issues", [])
            }

        first = asyncio.run(mcp.artifact_verify(
            repo_root=str(repo), confirm_full_pass=True, return_mode="full",
        ))
        assert "E319" not in codes(first)

        # The incident: a rename that left the old file in place, so two files carry one identity.
        source = next(repo.rglob(f"{real}.md"))
        stale = f"{real.rpartition('.')[0]}.manufacturing-planning-runs-nightly"
        source.with_name(f"{stale}.md").write_text(
            source.read_text(encoding="utf-8").replace(real, stale), encoding="utf-8"
        )
        clear_caches_for_repo(repo)

        second = asyncio.run(mcp.artifact_verify(repo_root=str(repo), return_mode="full"))

        assert "E319" in codes(second)
