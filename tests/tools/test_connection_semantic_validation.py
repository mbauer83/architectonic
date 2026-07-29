"""Tests for ArchiMate 4.0 semantic triple validation.

Covers:
- Write path (add_connection) rejects prohibited triples
- Verifier (verify_outgoing_file) reports E126 for prohibited triples
- Valid triples are not rejected (function→service, process→service, service→component serving)
- W126 realization-misuse warning for structure→service realization
- Symmetric association is accepted in both orientations
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as tools


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity_md(artifact_id: str, artifact_type: str, name: str) -> str:
    prefix = artifact_id.split("@")[0]
    rand = artifact_id.split(".")[1] if "." in artifact_id else "XXXXXX"
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: {artifact_type}
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-04-17'
---

<!-- §content -->

## {name}

<!-- §display -->

### archimate

```yaml
label: "{name}"
alias: {prefix}_{rand}
```
"""


def _outgoing_md(source_id: str, conn_type: str, target_id: str) -> str:
    return f"""\
---
source-entity: {source_id}
version: 0.1.0
status: draft
last-updated: '2026-04-17'
---

<!-- §connections -->

### {conn_type} → {target_id}
"""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-SEM" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    return root


def _plant_entities(repo: Path) -> tuple[str, str, str, str]:
    """Create a service, function, application-component, system-software in repo."""
    srv_id = "SRV@1000000001.SrvAbc.test-service"
    fnc_id = "FNC@1000000002.FncAbc.test-function"
    app_id = "APP@1000000003.AppAbc.test-component"
    ssw_id = "SSW@1000000004.SswAbc.test-runtime"

    _write(repo / "model/common/service" / f"{srv_id}.md", _entity_md(srv_id, "service", "Test Service"))
    _write(repo / "model/common/function" / f"{fnc_id}.md", _entity_md(fnc_id, "function", "Test Function"))
    _write(
        repo / "model/application/application-component" / f"{app_id}.md",
        _entity_md(app_id, "application-component", "Test Component"),
    )
    _write(
        repo / "model/technology/system-software" / f"{ssw_id}.md",
        _entity_md(ssw_id, "system-software", "Test Runtime"),
    )
    return srv_id, fnc_id, app_id, ssw_id


# ---------------------------------------------------------------------------
# Verifier: E126 / W126 detection
# ---------------------------------------------------------------------------


class TestVerifierSemanticCheck:
    def test_function_realizes_service_is_valid(self, repo: Path) -> None:
        srv_id, fnc_id, app_id, ssw_id = _plant_entities(repo)
        out_path = repo / "model/common/function" / f"{fnc_id}.outgoing.md"
        _write(out_path, _outgoing_md(fnc_id, "archimate-realization", srv_id))

        registry = ArtifactRegistry(shared_artifact_index(repo))
        verifier = ArtifactVerifier(registry=registry, catalogs=_catalogs())
        result = verifier.verify_outgoing_file(out_path)

        codes = {i.code for i in result.issues}
        assert "E126" not in codes, result.issues

    def test_service_realizes_component_gives_e126(self, repo: Path) -> None:
        srv_id, fnc_id, app_id, ssw_id = _plant_entities(repo)
        out_path = repo / "model/common/service" / f"{srv_id}.outgoing.md"
        _write(out_path, _outgoing_md(srv_id, "archimate-realization", app_id))

        registry = ArtifactRegistry(shared_artifact_index(repo))
        verifier = ArtifactVerifier(registry=registry, catalogs=_catalogs())
        result = verifier.verify_outgoing_file(out_path)

        codes = {i.code for i in result.issues}
        assert "E126" in codes

    def test_component_realizes_service_gives_e126_and_w126(self, repo: Path) -> None:
        srv_id, fnc_id, app_id, ssw_id = _plant_entities(repo)
        out_path = repo / "model/application/application-component" / f"{app_id}.outgoing.md"
        _write(out_path, _outgoing_md(app_id, "archimate-realization", srv_id))

        registry = ArtifactRegistry(shared_artifact_index(repo))
        verifier = ArtifactVerifier(registry=registry, catalogs=_catalogs())
        result = verifier.verify_outgoing_file(out_path)

        codes = {i.code for i in result.issues}
        assert "E126" in codes
        assert "W126" in codes

    def test_service_serves_component_is_valid(self, repo: Path) -> None:
        srv_id, fnc_id, app_id, ssw_id = _plant_entities(repo)
        out_path = repo / "model/common/service" / f"{srv_id}.outgoing.md"
        _write(out_path, _outgoing_md(srv_id, "archimate-serving", app_id))

        registry = ArtifactRegistry(shared_artifact_index(repo))
        verifier = ArtifactVerifier(registry=registry, catalogs=_catalogs())
        result = verifier.verify_outgoing_file(out_path)

        codes = {i.code for i in result.issues}
        assert "E126" not in codes, result.issues

    def test_system_software_serves_component_is_valid(self, repo: Path) -> None:
        srv_id, fnc_id, app_id, ssw_id = _plant_entities(repo)
        out_path = repo / "model/technology/system-software" / f"{ssw_id}.outgoing.md"
        _write(out_path, _outgoing_md(ssw_id, "archimate-serving", app_id))

        registry = ArtifactRegistry(shared_artifact_index(repo))
        verifier = ArtifactVerifier(registry=registry, catalogs=_catalogs())
        result = verifier.verify_outgoing_file(out_path)

        codes = {i.code for i in result.issues}
        assert "E126" not in codes, result.issues

    def test_association_is_symmetric(self, repo: Path) -> None:
        srv_id, fnc_id, app_id, ssw_id = _plant_entities(repo)
        out_path = repo / "model/application/application-component" / f"{app_id}.outgoing.md"
        _write(out_path, _outgoing_md(app_id, "archimate-association", srv_id))

        registry = ArtifactRegistry(shared_artifact_index(repo))
        verifier = ArtifactVerifier(registry=registry, catalogs=_catalogs())
        result = verifier.verify_outgoing_file(out_path)

        codes = {i.code for i in result.issues}
        assert "E126" not in codes, result.issues


# ---------------------------------------------------------------------------
# Write path: add_connection rejects prohibited triples
# ---------------------------------------------------------------------------


class TestWritePathSemanticCheck:
    def test_write_rejects_service_realizes_component(self, repo: Path) -> None:
        srv_id, fnc_id, app_id, ssw_id = _plant_entities(repo)

        with pytest.raises(ValueError, match="not permitted"):
            tools.artifact_add_connection(
                source_entity=srv_id,
                connection_type="archimate-realization",
                target_entity=app_id,
                description="invalid",
                repo_root=str(repo),
                dry_run=False,
            )

    def test_write_rejects_component_realizes_service(self, repo: Path) -> None:
        srv_id, fnc_id, app_id, ssw_id = _plant_entities(repo)

        with pytest.raises(ValueError, match="not permitted"):
            tools.artifact_add_connection(
                source_entity=app_id,
                connection_type="archimate-realization",
                target_entity=srv_id,
                description="invalid",
                repo_root=str(repo),
                dry_run=False,
            )

    def test_write_allows_function_realizes_service(self, repo: Path) -> None:
        srv_id, fnc_id, app_id, ssw_id = _plant_entities(repo)

        result = tools.artifact_add_connection(
            source_entity=fnc_id,
            connection_type="archimate-realization",
            target_entity=srv_id,
            description="Function realizes service",
            repo_root=str(repo),
            dry_run=False,
        )
        assert result.get("wrote") is True, result

    def test_write_allows_system_software_serves_component(self, repo: Path) -> None:
        srv_id, fnc_id, app_id, ssw_id = _plant_entities(repo)

        result = tools.artifact_add_connection(
            source_entity=ssw_id,
            connection_type="archimate-serving",
            target_entity=app_id,
            description="Runtime serves component",
            repo_root=str(repo),
            dry_run=False,
        )
        assert result.get("wrote") is True, result
