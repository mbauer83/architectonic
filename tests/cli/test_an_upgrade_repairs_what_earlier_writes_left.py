"""`arch-repair upgrade --commit` leaves a repository written by an earlier release verifying clean.

The fixture is the shape of a real repository's five capability views, minimised. Releases up to 0.11.1
wrote three things the current verifier refuses, none of them by a later edit:

* `entity-ids-used` listing occurrence statements — the diagram's own, and another diagram's that
  shared an alias — as if they were elements (E301). They were indexed as entities then; they are not.
* a body nesting one element inside another the model relates, with the relation missing from
  `connection-ids-used` (E316). A diagram carrying any statement was read as standalone, so neither the
  reconcile that would have listed the relation nor the rule that reports it ever looked.
* a connection file whose `source-entity` an edit had spelled short (W041).

The entities and connections are written through the tools; the two diagrams and the short source are
written as those releases left them, because no current tool can write them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from src.application.artifacts.parsing import normalize_puml_alias, standard_alias_of
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.artifact_id import stable_conn_id, stable_id
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.cli import arch_repair_upgrade as cli
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.verification.verifier_factory import build_artifact_verifier

VIEW = "ARC@1787699731.h7Tx5pN.plan-the-manufacture-of-a-part"
OTHER_VIEW = "ARC@1787723146.BXo3Qk_.obtain-a-manufacturing-assessment"


@pytest.fixture(autouse=True)
def _no_real_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "probe_backend_url", lambda *_a, **_k: False)


def _entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type, name=name, summary=f"Summary for {name}", dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _connect(repo: Path, source: str, connection_type: str, target: str) -> str:
    result = mcp.artifact_add_connection(
        source_entity=source, connection_type=connection_type, target_entity=target, dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result
    return stable_conn_id(f"{source}---{target}@@{connection_type}")


def _alias(entity_id: str) -> str:
    return normalize_puml_alias(standard_alias_of(entity_id))


def _diagram(diagram_id: str, elements: list[str], statements: list[str], occurrence_of: str, body: str) -> str:
    occurrence = f"{_alias(occurrence_of)}_x2"
    frontmatter = {
        "artifact-id": diagram_id, "artifact-type": "diagram", "name": diagram_id.rsplit(".", 1)[1],
        "version": "0.1.0", "status": "active", "diagram-type": "archimate-layered", "manual-layout": True,
        "entity-ids-used": [*elements, *statements],
        "connection-ids-used": [],
        "diagram-entities": {"occurrence": [{"id": occurrence, "visual_role": "drawn again"}]},
        "bindings": [{
            "id": f"bind-{occurrence}", "subject": {"kind": "entity", "id": occurrence},
            "correspondence_kind": "represents", "target": {"entity_id": occurrence_of},
            "visual_role": "drawn again",
        }],
        "last-updated": "2026-09-30T12:10:54Z",
    }
    head = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    return f"---\n{head}---\n@startuml\ntitle {frontmatter['name']}\n{body}\n@enduml\n"


@pytest.fixture()
def repo(tmp_path: Path) -> dict[str, str | Path]:
    root = tmp_path / "engagements" / "ENG-LEGACY" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    diagrams = root / "diagram-catalog" / "diagrams"
    diagrams.mkdir(parents=True)

    engine = _entity(root, "application-component", "CAD Model Engine Service")
    toolkit = _entity(root, "system-software", "CAD Exchanger Manufacturing Toolkit")
    capability = _entity(root, "capability", "Tenant Configuration")
    material = _entity(root, "business-object", "Material Catalogue")
    serving = _connect(root, toolkit, "archimate-serving", engine)
    association = _connect(root, capability, "archimate-association", material)

    body = (
        f'rectangle "Engine" <<application_component>> as {_alias(engine)} {{\n'
        f'  rectangle "Toolkit" <<system_software>> as {_alias(toolkit)}\n'
        "}\n"
        f'rectangle "Capability" <<capability>> as {_alias(capability)} {{\n'
        f'  rectangle "Catalogue" <<business_object>> as {_alias(material)}\n'
        "}\n"
        f'rectangle "Engine again" <<application_component>> as {_alias(engine)}_x2'
    )
    own, foreign = (f"{view}#occurrence/{_alias(engine)}_x2" for view in (VIEW, OTHER_VIEW))
    (diagrams / f"{VIEW}.puml").write_text(
        _diagram(VIEW, [engine, toolkit, capability, material], [foreign, own], engine, body), encoding="utf-8",
    )
    other_body = f'rectangle "Engine" <<application_component>> as {_alias(engine)}'
    (diagrams / f"{OTHER_VIEW}.puml").write_text(
        _diagram(OTHER_VIEW, [engine], [foreign], engine, other_body), encoding="utf-8",
    )
    (outgoing,) = root.glob(f"model/**/{toolkit}.outgoing.md")
    written_long = outgoing.read_text(encoding="utf-8")
    outgoing.write_text(
        written_long.replace(f"source-entity: {toolkit}", f"source-entity: {stable_id(toolkit)}"), encoding="utf-8",
    )

    for command in (["init", "-q"], ["config", "user.email", "t@t.com"], ["config", "user.name", "T"],
                    ["add", "-A"], ["commit", "-q", "-m", "as an earlier release left it"]):
        subprocess.run(["git", *command], cwd=root, check=True)
    return {"root": root, "toolkit": toolkit, "serving": serving, "association": association, "outgoing": outgoing}


def _findings(root: Path) -> dict[str, list[str]]:
    """Every finding the verifier makes, by file name, as `CODE message`."""
    registry = ArtifactRegistry(shared_artifact_index([root]))
    registry.refresh()
    verifier = build_artifact_verifier(registry, catalogs=process_runtime_catalogs(), check_puml_syntax=False)
    return {
        Path(str(result.path)).name: [f"{issue.code} {issue.message}" for issue in result.issues]
        for result in verifier.verify_all(root)
    }


def _codes(findings: dict[str, list[str]], name: str) -> set[str]:
    return {finding.split(" ", 1)[0] for finding in findings.get(name, [])}


def _stated(path: Path) -> dict[str, object]:
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def _upgraded(root: Path) -> None:
    assert cli.main_upgrade(["--repo-root", str(root), "--commit"]) == 0


def test_the_fixture_has_the_shape_the_current_verifier_refuses(repo: dict) -> None:
    root, outgoing = repo["root"], repo["outgoing"]
    findings = _findings(root)

    assert {"E301", "E316"} <= _codes(findings, f"{VIEW}.puml")
    assert "E301" in _codes(findings, f"{OTHER_VIEW}.puml")
    assert f"source-entity: {stable_id(repo['toolkit'])}\n" in outgoing.read_text(encoding="utf-8")


def test_the_upgraded_repository_verifies_clean(repo: dict) -> None:
    root = repo["root"]

    _upgraded(root)
    findings = _findings(root)

    errors = {name: [f for f in found if f.startswith("E")] for name, found in findings.items()}
    assert not any(errors.values()), errors


def test_the_upgrade_lists_the_nested_relations_and_keeps_every_element(repo: dict) -> None:
    root = repo["root"]
    before = _stated(root / "diagram-catalog" / "diagrams" / f"{VIEW}.puml")

    _upgraded(root)

    after = _stated(root / "diagram-catalog" / "diagrams" / f"{VIEW}.puml")
    assert after["connection-ids-used"] == [repo["serving"], repo["association"]]
    assert after["entity-ids-used"] == [eid for eid in before["entity-ids-used"] if "#" not in eid]
    assert after["diagram-entities"] == before["diagram-entities"]
    assert after["bindings"] == before["bindings"]


def test_the_connection_file_names_its_source_long(repo: dict) -> None:
    root, outgoing, toolkit = repo["root"], repo["outgoing"], repo["toolkit"]

    _upgraded(root)

    assert f"source-entity: {toolkit}\n" in outgoing.read_text(encoding="utf-8")


def test_a_second_upgrade_changes_nothing(repo: dict) -> None:
    root = repo["root"]
    _upgraded(root)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout

    _upgraded(root)

    again = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout
    assert again == head
    assert subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout == ""
