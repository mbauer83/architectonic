"""The AIBOM and datatype MCP tools, each asked something real — the last of the unnamed reads.

These were reachable only through the loop-over-every-tool gates, which prove a tool registers, serves
an object input schema and declares its four hints. None of them proves it *answers*: a read could emit
an empty BOM, or the same BOM whatever it was handed, and pass the whole suite.

Two kinds of tool here, tested two ways, on purpose:

* ``assurance_scan_ai_candidates`` and ``assurance_aibom_export`` are pure over their arguments, so the
  fixtures are this module's own and the assertions are exact.
* ``artifact_aibom_export``, ``artifact_aibom_coverage`` and ``artifact_query_datatype_types`` read the
  **real repository**, so nothing here asserts a count, a list or a position. Authoring an entity is
  the product working, and a test that failed for it would report a false regression far from the
  change that caused it. What is asserted is the invariant each count was standing in for — the
  document is well-formed CycloneDX, the coverage report accounts for exactly the components it
  found, the type catalogue is internally consistent.
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.infrastructure.mcp.mcp_artifact_server import mcp_read
from src.infrastructure.mcp.mcp_assurance_server import mcp_assurance_read


def _call(server: Any, tool: str, **arguments: object) -> dict[str, Any]:
    _unstructured, structured = asyncio.run(server.call_tool(tool, arguments))
    return structured


# ── Pure over their arguments ────────────────────────────────────────────────────────────────────


class TestScanAiCandidates:
    def test_an_ai_shaped_entity_is_ranked_and_a_plain_one_is_not(self) -> None:
        """Fed exactly what the tool's own description says to feed it: arch-repo-read's output.

        Under the scanner's older field names alone this returned a candidate whose `entity_id` was
        empty — a ranked list naming nothing the caller could go on to mark.
        """
        answer = _call(
            mcp_assurance_read,
            "assurance_scan_ai_candidates",
            entities=[
                {
                    "artifact_id": "TSV@1.aaaa.claude-inference-service",
                    "name": "Claude inference service",
                    "artifact_type": "technology-service",
                    "summary": "Hosts the model the scoring pipeline calls.",
                },
                {
                    "artifact_id": "BSP@1.bbbb.invoice-printing",
                    "name": "Invoice printing",
                    "artifact_type": "business-process",
                    "summary": "Prints invoices.",
                },
            ],
        )

        by_id = {str(c.get("entity_id", "")): c for c in answer["candidates"]}
        # Identity is the whole point of the answer: without it the caller cannot mark what was found.
        assert "TSV@1.aaaa.claude-inference-service" in by_id
        assert "BSP@1.bbbb.invoice-printing" not in by_id
        assert answer["count"] == len(answer["candidates"])

        candidate = by_id["TSV@1.aaaa.claude-inference-service"]
        # The type is read too, so the type bonus can apply — it only amplifies a name signal, and an
        # unread type silently withheld it from every entity fed in the repository's own vocabulary.
        assert str(candidate["entity_type"]) == "technology-service"
        assert any("technology-service" in str(r) for r in candidate["reasons"])

    def test_nothing_in_gives_nothing_out_rather_than_an_error(self) -> None:
        answer = _call(mcp_assurance_read, "assurance_scan_ai_candidates", entities=[])
        assert answer["candidates"] == []
        assert answer["count"] == 0

    def test_the_answer_says_marking_is_an_architecture_write(self) -> None:
        # The tool is assistive and there is deliberately no `assurance_mark_ai_component`; an agent
        # that took the scan as authoritative would mark nothing and think it had.
        answer = _call(mcp_assurance_read, "assurance_scan_ai_candidates", entities=[])
        assert "artifact_edit_entity" in str(answer["note"])


class TestAssuranceAibomExport:
    def test_each_component_given_reaches_the_document(self) -> None:
        answer = _call(
            mcp_assurance_read,
            "assurance_aibom_export",
            ai_components=[
                {"name": "Scoring model", "ai_role": "machine-learning-model", "version": "2.1"},
                {"name": "Training set", "ai_role": "dataset"},
            ],
            notes="quarterly baseline",
        )

        assert answer["component_count"] == 2
        bom = answer["bom"]
        assert bom["bomFormat"] == "CycloneDX"
        assert bom["specVersion"] == "1.6"
        assert {str(c["name"]) for c in bom["components"]} == {"Scoring model", "Training set"}

    def test_an_empty_inventory_is_still_a_well_formed_document(self) -> None:
        # An empty BOM is a legitimate answer — "we looked, there is nothing" — and must not be an
        # error or a document a consumer cannot parse.
        answer = _call(mcp_assurance_read, "assurance_aibom_export", ai_components=[])
        assert answer["component_count"] == 0
        assert answer["bom"]["bomFormat"] == "CycloneDX"
        assert answer["bom"]["components"] == []


# ── Reads of the real repository: invariants only ────────────────────────────────────────────────


class TestArtifactAibomExport:
    def test_the_document_is_well_formed_cyclonedx_whatever_the_model_holds(self) -> None:
        answer = _call(mcp_read, "artifact_aibom_export")
        bom = answer["bom"]

        assert bom["bomFormat"] == "CycloneDX"
        assert bom["specVersion"] == "1.6"
        assert isinstance(bom["serialNumber"], str) and bom["serialNumber"]
        assert isinstance(bom["components"], list)
        # The reported count is the document's own count, not a second tally that can disagree.
        assert answer["component_count"] == len(bom["components"])

    def test_every_component_it_emits_is_named(self) -> None:
        for component in _call(mcp_read, "artifact_aibom_export")["bom"]["components"]:
            assert str(component.get("name", "")), component

    def test_the_notes_a_caller_passes_are_carried_into_the_document(self) -> None:
        stamped = _call(mcp_read, "artifact_aibom_export", notes="ITEM-3 provenance check")
        assert "ITEM-3 provenance check" in str(stamped["bom"])


class TestArtifactAibomCoverage:
    def test_it_accounts_for_exactly_the_components_it_reports(self) -> None:
        answer = _call(mcp_read, "artifact_aibom_coverage")
        assert isinstance(answer["components"], list)
        assert isinstance(answer["unbound_roles"], list)

        for row in answer["components"]:
            # Each row names the component it is about and separates blocking from advisory: a report
            # that merged them would make an advisory gap look like a release blocker.
            assert str(row.get("artifact_id", "")), row
            assert isinstance(row.get("blocking_gaps", []), list), row
            assert isinstance(row.get("advisory_gaps", []), list), row

    def test_it_agrees_with_the_export_about_which_components_exist(self) -> None:
        # Two reads over one model; if they disagree, one of them is deriving the AI inventory its own
        # way, which is the duplication the shared aibom_service exists to prevent.
        exported = _call(mcp_read, "artifact_aibom_export")["component_count"]
        covered = len(_call(mcp_read, "artifact_aibom_coverage")["components"])
        assert covered == exported


class TestDatatypeTypeCatalogue:
    def test_it_offers_primitives_and_internally_consistent_classifiers(self) -> None:
        answer = _call(mcp_read, "artifact_query_datatype_types")

        assert answer["primitives"], "a datatype diagram cannot be authored with no primitive types"
        assert all(isinstance(p, str) and p for p in answer["primitives"])
        for classifier in answer["classifiers"]:
            # `type_id` is what a caller puts in `{kind: 'classifier', id: …}`, so an unlabelled or
            # unidentified row is one the caller cannot act on.
            assert str(classifier.get("type_id", "")), classifier
            assert str(classifier.get("label", "")), classifier

    def test_the_limit_bounds_the_page_and_the_cursor_says_whether_more_remain(self) -> None:
        page = _call(mcp_read, "artifact_query_datatype_types", limit=1)
        assert len(page["classifiers"]) <= 1
        # A truncated page must offer a way onward; an exhausted one must not invent one.
        full = _call(mcp_read, "artifact_query_datatype_types")
        if len(full["classifiers"]) > 1:
            assert page["next_cursor"] is not None

    def test_a_query_that_matches_nothing_answers_empty_rather_than_everything(self) -> None:
        answer = _call(mcp_read, "artifact_query_datatype_types", query="zzz-no-such-classifier-zzz")
        assert answer["classifiers"] == []
