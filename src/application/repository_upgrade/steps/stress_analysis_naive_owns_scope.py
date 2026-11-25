"""Carry a stress analysis written before its naive candidate owned the scope into the current form.

An analysis evaluates the architecture its naive candidate holds (owner, 2026-11-25). Before that it
asked a `question` and named its `scope-diagram` in the document. Now the document names the naive and,
optionally, the `context` the evaluation is made in, and the naive candidate names the diagram it is
drawn on. This step, for a repository that holds the earlier form:

* **the stress-analysis document type** — `question` and `scope-diagram` leave its frontmatter, and
  `context` joins it. Only those three properties are touched; a type adapted otherwise keeps the rest.
* **each analysis** — `question` is renamed `context`, its words kept, unless a context is already
  stated; `scope-diagram` moves to the naive candidate as the diagram it is drawn on, unless the naive
  already names one, and leaves the document either way.

Every other byte of each file is left as it was. Applying it twice changes nothing the second time.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from src.application.artifacts.parsing import extract_yaml_block
from src.application.change_sets.candidate_recorded_form import dump_candidate, load_candidate
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.steps._frontmatter_blocks import renamed_block, without_block
from src.domain.artifact_id import canonical_entity_key
from src.domain.repository.frontmatter import Frontmatter, read_frontmatter, replace_frontmatter_text
from src.domain.repository.repo_default_stress_analysis import (
    ANALYSIS_CONTEXT,
    NAIVE_CANDIDATE,
    STRESS_ANALYSIS,
    STRESS_ANALYSIS_SCHEMA,
)
from src.domain.repository.repo_layout import ARCH_DOC_SCHEMATA, ARCH_REPO
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding

_TYPE_FILE = f"{ARCH_REPO}/{ARCH_DOC_SCHEMATA}/{STRESS_ANALYSIS}.json"
#: The two frontmatter keys the earlier form had.
_QUESTION, _SCOPE_DIAGRAM = "question", "scope-diagram"
_TYPE_FINDING, _ANALYSIS_FINDING = "stress-analysis-type-asks-a-question", "stress-analysis-names-its-scope-diagram"


def _earlier_type(view: RepoUpgradeView) -> dict[str, Any] | None:
    """The stored document type, where it is in the earlier form."""
    text = view.read_text(_TYPE_FILE)
    stated = json.loads(text) if text else None
    properties = (stated or {}).get("frontmatter_schema", {}).get("properties", {})
    return stated if {_QUESTION, _SCOPE_DIAGRAM} & set(properties) else None


def _analyses(view: RepoUpgradeView) -> list[tuple[str, dict[str, object]]]:
    """Every analysis document and its frontmatter, by where the stored type files them."""
    text = view.read_text(_TYPE_FILE)
    folder = (json.loads(text) if text else {}).get("subdirectory") or STRESS_ANALYSIS_SCHEMA["subdirectory"]
    found = []
    for rel in view.list_files(f"**/{folder}/*.md"):
        frontmatter = extract_yaml_block(view.read_text(rel) or "")
        if isinstance(frontmatter, dict) and NAIVE_CANDIDATE in frontmatter:
            found.append((rel, frontmatter))
    return found


def _current_type(stated: dict[str, Any]) -> dict[str, Any]:
    properties = {
        key: value for key, value in stated["frontmatter_schema"]["properties"].items()
        if key not in (_QUESTION, _SCOPE_DIAGRAM)
    }
    properties.setdefault(ANALYSIS_CONTEXT, {"type": "string"})
    return {**stated, "frontmatter_schema": {**stated["frontmatter_schema"], "properties": properties}}


def _current_analysis(content: str) -> str:
    """The document with `question` read as `context`, unless one is stated, and no `scope-diagram`."""
    reading = read_frontmatter(content)
    frontmatter = extract_yaml_block(content)
    if not isinstance(frontmatter, dict) or not isinstance(reading, Frontmatter):
        return content
    text = without_block(reading.text, _SCOPE_DIAGRAM)
    text = without_block(text, _QUESTION) if ANALYSIS_CONTEXT in frontmatter else renamed_block(
        text, _QUESTION, ANALYSIS_CONTEXT,
    )
    return replace_frontmatter_text(content, text)


class StressAnalysisNaiveOwnsScopeStep:
    id = "stress-analysis-naive-owns-scope"
    version = 1
    description = "Move a stress analysis's scope diagram to its naive candidate, and its question to its context"
    scanned_surface: ScannedSurface = "profiles"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        findings = [] if _earlier_type(view) is None else [UpgradeFinding(
            step_id=self.id, finding_id=f"{_TYPE_FINDING}:{_TYPE_FILE}", location=_TYPE_FILE,
            description="the stress-analysis type states a question and a scope diagram",
            severity="info", auto_migratable=True,
            rewrite_summary="state an optional context instead; the naive candidate holds the diagram",
        )]
        return findings + [
            UpgradeFinding(
                step_id=self.id, finding_id=f"{_ANALYSIS_FINDING}:{rel}", location=rel,
                description="the analysis states a question or names its scope diagram",
                severity="info", auto_migratable=True,
                rewrite_summary="read the question as the context; give the scope diagram to the naive candidate",
            )
            for rel, frontmatter in _analyses(view)
            if _QUESTION in frontmatter or _SCOPE_DIAGRAM in frontmatter
        ]

    def apply(
        self, view: RepoUpgradeView, writer: RepoUpgradeWriter, findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        return [self._applied(view, writer, finding) for finding in findings]

    def _applied(self, view: RepoUpgradeView, writer: RepoUpgradeWriter, finding: UpgradeFinding) -> AppliedFinding:
        content = view.read_text(finding.location)
        if content is None:
            return AppliedFinding(finding=finding, outcome="error", detail="file no longer exists")
        if finding.location == _TYPE_FILE:
            stated = _earlier_type(view)
            if stated is None:
                return AppliedFinding(finding=finding, outcome="skipped", detail="already current")
            writer.write_text(_TYPE_FILE, json.dumps(_current_type(stated), indent=2) + "\n")
            return AppliedFinding(finding=finding, outcome="applied")
        frontmatter = extract_yaml_block(content)
        if isinstance(frontmatter, dict) and (diagram := frontmatter.get(_SCOPE_DIAGRAM)):
            refusal = _drawn_on(view, writer, str(frontmatter.get(NAIVE_CANDIDATE) or ""), str(diagram))
            if refusal:
                return AppliedFinding(finding=finding, outcome="error", detail=refusal)
        writer.write_text(finding.location, _current_analysis(content))
        return AppliedFinding(finding=finding, outcome="applied")


def _drawn_on(view: RepoUpgradeView, writer: RepoUpgradeWriter, naive: str, diagram: str) -> str | None:
    """Give the naive candidate *diagram* to be drawn on, unless it names one; why not, where it cannot."""
    key = canonical_entity_key(naive)
    for rel in view.list_files("**/*.candidate.yaml"):
        candidate = load_candidate(view.read_text(rel) or "")
        if canonical_entity_key(candidate.id) == key:
            if candidate.diagram is None:
                writer.write_text(rel, dump_candidate(replace(candidate, diagram=diagram)))
            return None
    return f"the naive candidate {naive} is not stored, so the scope diagram {diagram} has no candidate to go to"
