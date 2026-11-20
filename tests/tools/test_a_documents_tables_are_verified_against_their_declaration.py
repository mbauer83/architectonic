"""What the verifier says about a document's typed tables, and what it leaves a document free to be.

**Refusal blocks; narrowing warns.** A document being filled in stays writable: a missing table, a
column out of step, an empty required cell, a value outside its enum, a reference to the wrong kind
of thing and a row naming a row that is gone are warnings. Two things are errors, because each leaves
something that cannot be read: a cell that is not of its column's type, and a row id that is
malformed or carried twice.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from src.application.artifacts.document_schema import DocumentSchema
from src.application.artifacts.document_table_rows import read_document_tables
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.application.verification.artifact_verifier_types import VerificationResult
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.document import create_document
from src.infrastructure.write.artifact_write.types import WriteResult
from tests.support.typed_table_documents import (
    ARCHITECTURE_EVALUATION,
    EXAMPLE_TYPES,
    STRESS_ANALYSIS,
    adr_in,
    document_path,
    document_text,
    document_type,
    entity_in,
    link_to,
    raw_document_type,
    repository_in,
    runtime_catalogs,
    table_of,
    table_text,
)

_TABLE_CODES = frozenset({"W162", "W163", "W164", "W165", "W166", "W167", "W168", "E162", "E163"})

Rows = dict[str, list[dict[str, str]]]
Stress = tuple[Path, DocumentSchema, Path, Rows]


def _verifier(repo: Path) -> ArtifactVerifier:
    return ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=runtime_catalogs())


def _complete_stress_analysis(repo: Path, doc: Path) -> Rows:
    """Every table of a stress analysis with nothing left to say about it."""
    requirement = link_to(entity_in(repo, "requirement", "survive-a-provider-outage"), written_in=doc)
    goal = link_to(entity_in(repo, "goal", "keep-selling"), written_in=doc)
    component = link_to(entity_in(repo, "application-component", "checkout"), written_in=doc)
    return {
        "stressors": [
            {"stressor": "The payment provider is down", "origin": "drawn", "plausible": "true", "set": "design",
             "end_state": "E1"},
            {"stressor": "The provider doubles its fees", "set": "test", "end_state": "E1"},
        ],
        "end-states": [{"end_state": "Orders cannot be paid", "required_behaviour": requirement, "affects": goal}],
        "adaptations": [
            {"end_states": "E1", "candidate_architecture": "queue-payments", "integration": "candidate"}
        ],
        "incidence": [{"stressor": "S1", "component": component, "note": "calls the provider inline"}],
        "survival": [{"stressor": "S2", "naive_survives": "false", "integrated_survives": "true"}],
    }


def _written(schema: DocumentSchema, rows: Rows, texts: Mapping[str, str] | None = None, **frontmatter: str) -> str:
    tables = {name: table_text(table_of(schema, name), table_rows) for name, table_rows in rows.items()}
    return document_text(schema, tables | dict(texts or {}), **frontmatter)


def _verify(repo: Path, doc: Path, content: str) -> VerificationResult:
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(content, encoding="utf-8")
    return _verifier(repo).verify_document_file(doc)


def _messages(result: VerificationResult) -> str:
    return "\n".join(issue.message for issue in result.issues)


def _table_findings(result: VerificationResult) -> list[tuple[str, str]]:
    return [(issue.code, str(issue.severity)) for issue in result.issues if issue.code in _TABLE_CODES]


@pytest.fixture
def stress(tmp_path: Path) -> Stress:
    repo = repository_in(tmp_path, STRESS_ANALYSIS)
    schema = document_type(STRESS_ANALYSIS)
    doc = document_path(repo, schema)
    return repo, schema, doc, _complete_stress_analysis(repo, doc)


class TestACompleteDocumentHasNothingSaidAboutIt:
    def test_a_complete_stress_analysis(self, stress: Stress) -> None:
        repo, schema, doc, rows = stress

        result = _verify(repo, doc, _written(schema, rows))

        assert [(issue.code, issue.message) for issue in result.issues] == []

    def test_a_complete_evaluation(self, tmp_path: Path) -> None:
        repo = repository_in(tmp_path, ARCHITECTURE_EVALUATION)
        schema = document_type(ARCHITECTURE_EVALUATION)
        doc = document_path(repo, schema)
        scenario = link_to(entity_in(repo, "requirement", "fail-over-in-30s"), written_in=doc)
        decision = link_to(adr_in(repo, "replicate-the-store"), written_in=doc)
        goal = link_to(entity_in(repo, "goal", "always-on"), written_in=doc)
        rows: Rows = {
            "utility": [{"quality": "Availability", "refinement": "Failover", "scenario": scenario,
                         "importance": "H", "difficulty": "M"}],
            "analysis": [{"scenario": "U1", "decision": decision, "decided": "true", "effect": "+",
                          "sensitivity_point": "1", "risk": "R1", "nonrisk": "N1"}],
            "risks": [{"risk": "Replication lag loses writes", "about": decision}],
            "nonrisks": [{"nonrisk": "Reads stay served", "assumption": "A replica is always in sync"}],
            "themes": [{"theme": "Data loss on failover", "risks": "R1", "threatens": goal}],
        }

        result = _verify(repo, doc, _written(schema, rows, method="atam"))

        assert [(issue.code, issue.message) for issue in result.issues] == []

    @pytest.mark.parametrize("doc_type", EXAMPLE_TYPES)
    def test_a_document_with_every_table_empty(self, tmp_path: Path, doc_type: str) -> None:
        repo = repository_in(tmp_path, doc_type)
        schema = document_type(doc_type)

        result = _verify(repo, document_path(repo, schema), document_text(schema, {}, method="atam"))

        assert _table_findings(result) == []


class TestWhatIsNotThereYetWarns:
    """Each of these leaves the document valid: it can still be saved."""

    def _one(
        self, stress: Stress, *, texts: Mapping[str, str] | None = None
    ) -> tuple[list[tuple[str, str]], VerificationResult]:
        repo, schema, doc, rows = stress
        result = _verify(repo, doc, _written(schema, rows, texts))
        assert result.valid, result.errors
        return _table_findings(result), result

    def test_a_declared_table_missing_from_its_section(self, stress: Stress) -> None:
        findings, result = self._one(stress, texts={"end-states": "Not yet named."})

        assert ("W162", "warning") in findings
        assert "add one headed Id | End state | Required behaviour | Affects" in _messages(result)

    def test_a_declared_column_missing_from_the_header(self, stress: Stress) -> None:
        table = "| Id | Stressor | Naive survives |\n|---|---|---|\n| T1 | S2 | false |"

        findings, result = self._one(stress, texts={"survival": table})

        assert findings == [("W163", "warning")]
        assert "has no column 'Integrated survives'" in result.issues[0].message

    def test_a_missing_required_column_is_said_once_and_not_per_row(
        self, stress: Stress
    ) -> None:
        table = "| Id | Naive survives |\n|---|---|\n| T1 | false |\n| T2 | true |"

        findings, _ = self._one(stress, texts={"survival": table})

        assert findings == [("W163", "warning"), ("W163", "warning")]

    def test_a_column_the_declaration_does_not_have(self, stress: Stress) -> None:
        table = (
            "| Id | Stressor | Naive survives | Integrated survives | Owner |\n|---|---|---|---|---|\n"
            "| T1 | S2 | false | true | me |"
        )

        findings, result = self._one(stress, texts={"survival": table})

        assert findings == [("W164", "warning")]
        assert "'Owner'" in result.issues[0].message

    def test_a_required_cell_left_empty(self, stress: Stress) -> None:
        stress[3]["stressors"][1]["set"] = ""

        findings, result = self._one(stress)

        assert findings == [("W165", "warning")]
        assert "Table 'stressors' row S2: (root): 'set' is a required property" in result.issues[0].message

    def test_a_value_outside_its_enum(self, stress: Stress) -> None:
        stress[3]["stressors"][0]["origin"] = "guessed"

        findings, result = self._one(stress)

        assert findings == [("W165", "warning")]
        assert "row S1: origin: 'guessed' is not one of ['drawn', 'elicited', 'model-prompted']" in (
            result.issues[0].message
        )

    def test_a_reference_to_something_the_column_does_not_take(
        self, stress: Stress
    ) -> None:
        stress[3]["end-states"][0]["required_behaviour"] = stress[3]["end-states"][0]["affects"]

        findings, result = self._one(stress)

        assert findings == [("W166", "warning")]
        assert "links keep-selling (entity, type 'goal'); the column takes" in result.issues[0].message

    def test_a_reference_to_nothing(self, stress: Stress) -> None:
        stress[3]["incidence"][0]["component"] = "[gone](../../model/application-component/gone.md)"

        findings, _ = self._one(stress)

        assert findings == [("W166", "warning")]

    def test_a_row_without_an_id(self, stress: Stress) -> None:
        repo, schema, doc, rows = stress
        survival = table_text(table_of(schema, "survival"), rows.pop("survival"), row_ids=[""])

        findings, result = self._one((repo, schema, doc, rows), texts={"survival": survival})

        assert findings == [("W167", "warning")]
        assert "such as T1" in result.issues[0].message

    def test_a_row_cell_naming_a_row_that_is_not_there(self, stress: Stress) -> None:
        stress[3]["adaptations"][0]["end_states"] = "E1, E7"

        findings, result = self._one(stress)

        assert findings == [("W168", "warning")]
        assert "names row E7, which table 'end-states' does not hold" in result.issues[0].message

    def test_a_row_of_another_table_is_not_a_row_of_this_one(self, stress: Stress) -> None:
        stress[3]["incidence"][0]["stressor"] = "E1"

        findings, _ = self._one(stress)

        assert findings == [("W168", "warning")]


class TestWhatCannotBeReadIsRefused:
    def _one(
        self, stress: Stress, *, texts: Mapping[str, str] | None = None
    ) -> tuple[list[tuple[str, str]], VerificationResult]:
        repo, schema, doc, rows = stress
        result = _verify(repo, doc, _written(schema, rows, texts))
        assert not result.valid
        return _table_findings(result), result

    @pytest.mark.parametrize(
        ("table", "column", "cell"),
        [
            ("stressors", "plausible", "probably"),
            ("end-states", "required_behaviour", "the outage requirement"),
            ("incidence", "stressor", "the first one"),
            ("adaptations", "end_states", "E1 and E2"),
        ],
    )
    def test_a_cell_that_is_not_of_its_columns_type(
        self, stress: Stress, table: str, column: str, cell: str
    ) -> None:
        stress[3][table][0][column] = cell

        findings, result = self._one(stress)

        assert findings == [("E162", "error")]
        assert f"Table '{table}' row" in result.issues[0].message

    def test_an_unreadable_required_cell_is_not_also_called_empty(
        self, stress: Stress
    ) -> None:
        stress[3]["incidence"][0]["component"] = "the checkout"

        findings, _ = self._one(stress)

        assert findings == [("E162", "error")]

    def test_two_rows_carrying_one_id(self, stress: Stress) -> None:
        repo, schema, doc, rows = stress
        stressors = table_text(table_of(schema, "stressors"), rows.pop("stressors"), row_ids=["S1", "S1"])

        findings, result = self._one((repo, schema, doc, rows), texts={"stressors": stressors})

        assert ("E163", "error") in findings
        assert "2 rows carry the id 'S1'" in _messages(result)

    @pytest.mark.parametrize("row_id", ["S-1", "1", "s1", "E1", "first"])
    def test_an_id_that_is_not_of_its_tables_form(
        self, stress: Stress, row_id: str
    ) -> None:
        repo, schema, doc, rows = stress
        rows["stressors"] = rows["stressors"][:1]
        rows["survival"] = []
        stressors = table_text(table_of(schema, "stressors"), rows.pop("stressors"), row_ids=[row_id])
        rows["incidence"][0]["stressor"] = ""

        findings, result = self._one((repo, schema, doc, rows), texts={"stressors": stressors})

        assert ("E163", "error") in findings
        assert "write it as S and a number, such as S1" in _messages(result)


class TestWhatIsSaidElsewhereIsNotSaidTwice:
    def test_a_missing_section_is_the_sections_finding_and_not_the_tables(self, tmp_path: Path) -> None:
        repo = repository_in(tmp_path, STRESS_ANALYSIS)
        schema = document_type(STRESS_ANALYSIS)
        content = document_text(schema, {}).replace("## Test\n", "## Trial\n")

        result = _verify(repo, document_path(repo, schema), content)

        assert [issue.code for issue in result.issues] == ["E154"]

    def test_a_term_that_does_not_expand_is_the_code_a_sections_terms_use(self, tmp_path: Path) -> None:
        repo = repository_in(tmp_path, STRESS_ANALYSIS)
        raw = raw_document_type(STRESS_ANALYSIS)
        raw["sections"][4]["tables"][0]["columns"][1]["to"] = ["componnent"]
        (repo / ".arch-repo" / "documents" / f"{STRESS_ANALYSIS}.json").write_text(json.dumps(raw), encoding="utf-8")
        schema = document_type(STRESS_ANALYSIS)

        result = _verify(repo, document_path(repo, schema), document_text(schema, {}))

        assert [(issue.code, str(issue.severity)) for issue in result.issues] == [("W157", "warning")]
        assert "table 'incidence' column 'Component': componnent" in result.issues[0].message


def _create(repo: Path, doc_type: str, body: str | None, *, dry_run: bool) -> WriteResult:
    return create_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _: None,
        doc_type=doc_type,
        title="Checkout under stress",
        body=body,
        keywords=None,
        extra_frontmatter={"method": "atam"} if doc_type == ARCHITECTURE_EVALUATION else None,
        artifact_id=None,
        version="0.1.0",
        status="draft",
        last_updated="2026-11-20",
        dry_run=dry_run,
    )


def _body_of(content: str) -> str:
    return content.split("\n---\n", 1)[1]


class TestCreatingADocumentScaffoldsItsTables:
    @pytest.mark.parametrize("doc_type", EXAMPLE_TYPES)
    def test_every_declared_table_is_there_whole_and_empty(self, tmp_path: Path, doc_type: str) -> None:
        repo = repository_in(tmp_path, doc_type)
        schema = document_type(doc_type)

        created = _create(repo, doc_type, None, dry_run=True)

        assert created.content is not None
        read = read_document_tables(created.path, created.content, schema)
        assert read.tables != ()
        for table in read.tables:
            assert (table.found, table.rows, table.missing_columns, table.undeclared_columns) == (True, (), (), ())
        assert created.verification is not None
        assert created.verification["issues"] == []

    def test_a_table_sits_in_its_own_section_under_the_sections_starter(self, tmp_path: Path) -> None:
        repo = repository_in(tmp_path, STRESS_ANALYSIS)

        created = _create(repo, STRESS_ANALYSIS, None, dry_run=True)

        assert created.content is not None
        survival = "## Test\n\n| Id | Stressor | Naive survives | Integrated survives |\n|---|---|---|---|\n"
        assert survival in created.content
        assert "## Naive Architecture\n\n<!-- Expected links for this section: suggested: diagram:@all -->\n" in (
            created.content
        )

    def test_a_scaffolded_document_is_written(self, tmp_path: Path) -> None:
        repo = repository_in(tmp_path, STRESS_ANALYSIS)

        assert _create(repo, STRESS_ANALYSIS, None, dry_run=False).wrote


class TestADocumentInProgressStaysWritable:
    def test_incomplete_rows_are_written_and_warned_about(self, tmp_path: Path) -> None:
        repo = repository_in(tmp_path, STRESS_ANALYSIS)
        schema = document_type(STRESS_ANALYSIS)
        rows: Rows = {"stressors": [{"stressor": "The provider is down"}, {"kind": "market", "end_state": "E4"}]}

        created = _create(repo, STRESS_ANALYSIS, _body_of(_written(schema, rows)), dry_run=False)

        assert created.wrote
        assert created.verification is not None
        assert sorted(issue["code"] for issue in created.verification["issues"]) == ["W165", "W165", "W165", "W168"]

    def test_a_cell_that_cannot_be_read_is_refused_with_the_cell_named(self, tmp_path: Path) -> None:
        repo = repository_in(tmp_path, STRESS_ANALYSIS)
        schema = document_type(STRESS_ANALYSIS)
        rows: Rows = {"stressors": [{"stressor": "The provider is down", "set": "design", "plausible": "likely"}]}

        created = _create(repo, STRESS_ANALYSIS, _body_of(_written(schema, rows)), dry_run=False)

        assert not created.wrote
        assert created.error_messages == [
            "Table 'stressors' row S1 column 'Plausible': Cannot decode 'likely' as boolean; "
            "expected literal 'true' or 'false'"
        ]
