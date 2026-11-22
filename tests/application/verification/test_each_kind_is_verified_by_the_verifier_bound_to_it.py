"""A file is verified by the verifier bound to its kind, and a kind with none bound is unverified.

**The defect this replaces.** `verify_standalone_artifact` sent an icon to the icon verifier and every
other file to the document verifier. Two standalone kinds made that look like a choice; a third would
have been read as a document and passed or failed on a document's rules, without anyone having
decided it should. The MCP tool, the write preview and the bulk write each held their own `match` from
kind to method beside it, and the bulk one sent a matrix diagram to the PlantUML verifier.

**What holds now.** The bindings are declared once, at the composition layer, and checked against the
kind table at startup; dispatch looks the kind up and has no default arm. A kind with no verifier
answers `unverified`, which is never counted as passed — so a verifier built without bindings fails
closed instead of passing what it never looked at.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.application.verification.kind_verification import KindBinding, KindVerifier
from src.domain.repository.artifact_location import ARTIFACT_KIND_NAMES, ARTIFACT_KINDS, artifact_kind
from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs
from src.infrastructure.mcp.artifact_mcp.verify_tools import artifact_verify
from src.infrastructure.verification.kind_bindings import KIND_BINDINGS, kind_binding_contradictions
from tests.support.icon_files import write_icon

_DOCUMENT = """---
artifact-id: ADR@1790000000.abcdef.a-decision
artifact-type: document
doc-type: adr
title: A decision
status: accepted
---

## Context
"""


@pytest.fixture(scope="module")
def catalogs():
    return build_runtime_catalogs(build_module_registry())


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    for directory in ("model", "docs/adr", "diagram-catalog/diagrams", "scratchpads/thinking"):
        (root / directory).mkdir(parents=True)
    return root


def _verifier(catalogs, bindings=KIND_BINDINGS) -> ArtifactVerifier:
    return ArtifactVerifier(check_puml_syntax=False, catalogs=catalogs, kind_bindings=bindings)


# ── The bindings against the table ─────────────────────────────────────────────


def test_every_kind_of_the_table_is_bound_and_nothing_else_is() -> None:
    assert set(KIND_BINDINGS) == set(ARTIFACT_KIND_NAMES)
    assert list(kind_binding_contradictions()) == []


def test_a_kind_is_unverified_exactly_when_its_row_says_so() -> None:
    for kind in ARTIFACT_KINDS:
        assert (KIND_BINDINGS[kind.name].verifier is None) == (kind.verification == "unverified"), kind.name


def test_every_bound_verifier_declares_what_it_checks() -> None:
    for name, binding in KIND_BINDINGS.items():
        assert binding.verifier is None or binding.verifier.rule_codes, name


_SOME_VERIFIER = KindVerifier(verify=lambda host, path, snapshot: VerificationResult(path, "entity"),
                              rule_codes=frozenset({"E001"}))


@pytest.mark.parametrize(
    ("bindings", "says"),
    [
        pytest.param({k: v for k, v in KIND_BINDINGS.items() if k != "icon"}, "icon kind has no binding",
                     id="a-kind-left-unbound"),
        pytest.param({**KIND_BINDINGS, "icon": KindBinding(verifier=None)}, "icon kind is verified",
                     id="a-verified-kind-with-no-verifier"),
        pytest.param({**KIND_BINDINGS, "scratchpad": KindBinding(verifier=_SOME_VERIFIER)},
                     "scratchpad kind is declared unverified", id="an-unverified-kind-with-a-verifier"),
        pytest.param({**KIND_BINDINGS, "icon": KindBinding(verifier=replace(_SOME_VERIFIER, rule_codes=frozenset()))},
                     "declares no rule codes", id="a-verifier-that-checks-nothing"),
        pytest.param({**KIND_BINDINGS, "matrix": KindBinding(verifier=None)}, "does not declare",
                     id="a-binding-for-no-kind"),
    ],
)
def test_bindings_that_contradict_the_table_are_refused_by_name(bindings, says: str) -> None:
    refusals = list(kind_binding_contradictions(ARTIFACT_KINDS, bindings))

    assert len(refusals) == 1 and says in refusals[0], refusals


def test_startup_refuses_bindings_that_contradict_the_table(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.application.startup_validation import RegistryConsistencyError
    from src.infrastructure import app_bootstrap

    monkeypatch.setattr(app_bootstrap, "kind_binding_contradictions", lambda: iter(["the icon kind has no binding"]))

    with pytest.raises(RegistryConsistencyError, match="icon kind has no binding"):
        app_bootstrap.build_module_registry()


# ── Dispatch ───────────────────────────────────────────────────────────────────


def test_a_file_is_sent_to_the_verifier_of_its_own_kind(catalogs, repo: Path) -> None:
    (repo / "docs/adr/ADR@1790000000.abcdef.a-decision.md").write_text(_DOCUMENT, encoding="utf-8")
    icon = write_icon(repo)

    results = _verifier(catalogs)._verify_standalone_artifacts(repo)

    assert {(r.path.name, r.file_type, r.outcome) for r in results} == {
        ("ADR@1790000000.abcdef.a-decision.md", "document", "verified"),
        (icon.name, "icon", "verified"),
    }


def test_a_kind_left_unbound_is_unverified_rather_than_verified_as_another(catalogs, repo: Path) -> None:
    """The regression: an icon with no verifier of its own used to be verified as a document."""
    icon = write_icon(repo)
    without_icons = {**KIND_BINDINGS, "icon": KindBinding(verifier=None)}

    [result] = _verifier(catalogs, without_icons)._verify_standalone_artifacts(repo)

    assert (result.path, result.file_type, result.outcome) == (icon, "icon", "unverified")
    assert not result.valid, "a file nothing verified must not count as passed"


def test_a_verifier_built_without_bindings_verifies_no_kind(catalogs, repo: Path) -> None:
    icon = write_icon(repo)

    result = ArtifactVerifier(check_puml_syntax=False, catalogs=catalogs).verify_as("icon", icon)

    assert result.outcome == "unverified" and not result.valid
    assert "UNVERIFIED" in repr(result)


def test_an_unverified_result_is_not_passed_even_without_findings() -> None:
    verified = VerificationResult(Path("x.md"), "document")
    unverified = VerificationResult(Path("x.md"), "document", outcome="unverified")
    warned = VerificationResult(Path("x.md"), "document", [Issue(Severity.WARNING, "W001", "w", "x")])

    assert verified.valid and warned.valid and not unverified.valid


def test_asking_to_verify_a_scratchpad_answers_unverified_not_not_an_artifact(repo: Path) -> None:
    pad = repo / "scratchpads/thinking/SCR@1790000000.abcdef.some-thinking.scratchpad.yaml"
    pad.write_text("artifact-id: SCR@1790000000.abcdef.some-thinking\n", encoding="utf-8")
    assert artifact_kind("scratchpad").verification == "unverified"

    result = asyncio.run(artifact_verify(str(pad), repo_root=str(repo), repo_scope="engagement"))

    assert (result["file_type"], result["outcome"], result["valid"]) == ("scratchpad", "unverified", False)


def test_a_matrix_diagram_is_verified_as_a_matrix(catalogs, repo: Path) -> None:
    """The bulk write used to send any diagram it re-checked to the PlantUML verifier."""
    seen: list[str] = []

    class Host:
        def verify_diagram_file(self, path, *, snapshot=None):
            seen.append("plantuml")
            return VerificationResult(path, "diagram")

        def verify_matrix_diagram_file(self, path, *, snapshot=None):
            seen.append("matrix")
            return VerificationResult(path, "diagram")

    verify = KIND_BINDINGS["diagram"].verifier.verify
    verify(Host(), repo / "diagram-catalog/diagrams/MAT@1.a.x.md", None)
    verify(Host(), repo / "diagram-catalog/diagrams/ARC@1.a.x.puml", None)

    assert seen == ["matrix", "plantuml"]
