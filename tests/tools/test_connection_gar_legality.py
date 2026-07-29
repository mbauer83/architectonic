"""Connection legality for global-artifact-reference proxies.

A GAR carries EXACTLY the permitted connections of the entity type (and specialization)
it references — resolved per instance — with one tier invariant: the global object (and
thus its reference) is never the SOURCE of a directed relationship. Only incoming and
symmetric relationships may attach to a GAR.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from src.application.global_reference_endpoints import effective_endpoint
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.connection import add_connection


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())


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
last-updated: '2026-01-01'
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


def _gar_md(gar_id: str, referenced_id: str, referenced_entity_type: str, name: str) -> str:
    return f"""\
---
artifact-id: {gar_id}
artifact-type: global-artifact-reference
name: {name}
version: 0.1.0
status: active
last-updated: '2026-01-01'
global-artifact-id: {referenced_id}
global-artifact-type: entity
global-artifact-entity-type: {referenced_entity_type}
---

<!-- §content -->

## {name}

Engagement-repo proxy for promoted entity `{referenced_id}`.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
label: "{name}"
alias: GAR_proxy
```
"""


def _outgoing_md(source_id: str, conn_type: str, target_id: str) -> str:
    return f"""\
---
source-entity: {source_id}
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

<!-- §connections -->

### {conn_type} → {target_id}
"""


_REQ_ID = "REQ@1000000401.GarSrc.local-requirement"
_GLOBAL_REQ_ID = "REQ@1000000402.GarTgt.global-requirement"
_GAR_ID = "GAR@1000000403.GarPrx.global-requirement"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-GAR" / "architecture-repository"
    _write(
        root / "model/motivation/requirement" / f"{_REQ_ID}.md",
        _entity_md(_REQ_ID, "requirement", "Local Requirement"),
    )
    _write(
        root / "model/common/global-artifact-reference" / f"{_GAR_ID}.md",
        _gar_md(_GAR_ID, _GLOBAL_REQ_ID, "requirement", "Global Requirement"),
    )
    return root


def _deps(root: Path) -> tuple[ArtifactRegistry, ArtifactVerifier]:
    registry = ArtifactRegistry(shared_artifact_index(root))
    return registry, ArtifactVerifier(registry=registry, catalogs=_catalogs())


class TestEffectiveEndpoint:
    def test_gar_resolves_to_cached_referenced_type_when_record_unreachable(self, repo: Path) -> None:
        registry, _ = _deps(repo)
        endpoint = effective_endpoint(registry, _GAR_ID)
        assert endpoint.is_global_reference
        assert endpoint.entity_type == "requirement"

    def test_plain_entity_resolves_to_itself(self, repo: Path) -> None:
        registry, _ = _deps(repo)
        endpoint = effective_endpoint(registry, _REQ_ID)
        assert not endpoint.is_global_reference
        assert endpoint.entity_type == "requirement"


class TestWritePath:
    def test_directed_connection_to_gar_uses_referenced_type_surface(self, repo: Path) -> None:
        registry, verifier = _deps(repo)
        result = add_connection(
            repo_root=repo,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            source_entity=_REQ_ID,
            connection_type="archimate-composition",  # requirement→requirement permits this
            target_entity=_GAR_ID,
            description="Sub-requirement via global reference.",
            version="0.1.0",
            status="draft",
            last_updated=None,
            dry_run=True,
        )
        assert result.content is not None
        assert f"### archimate-composition → {_GAR_ID}" in result.content

    def test_gar_as_source_of_directed_connection_is_rejected(self, repo: Path) -> None:
        registry, verifier = _deps(repo)
        with pytest.raises(ValueError, match="never depends on engagement content"):
            add_connection(
                repo_root=repo,
                registry=registry,
                verifier=verifier,
                clear_repo_caches=lambda p: None,
                source_entity=_GAR_ID,
                connection_type="archimate-composition",
                target_entity=_REQ_ID,
                description=None,
                version="0.1.0",
                status="draft",
                last_updated=None,
                dry_run=True,
            )

    def test_symmetric_connection_with_gar_source_is_permitted(self, repo: Path) -> None:
        registry, verifier = _deps(repo)
        result = add_connection(
            repo_root=repo,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            source_entity=_GAR_ID,
            connection_type="archimate-association",
            target_entity=_REQ_ID,
            description=None,
            version="0.1.0",
            status="draft",
            last_updated=None,
            dry_run=True,
        )
        assert result.content is not None

    def test_illegal_type_through_the_reference_still_rejected(self, repo: Path) -> None:
        registry, verifier = _deps(repo)
        with pytest.raises(ValueError, match="resolved through the global reference"):
            add_connection(
                repo_root=repo,
                registry=registry,
                verifier=verifier,
                clear_repo_caches=lambda p: None,
                source_entity=_REQ_ID,
                connection_type="archimate-serving",  # requirement→requirement never permits serving
                target_entity=_GAR_ID,
                description=None,
                version="0.1.0",
                status="draft",
                last_updated=None,
                dry_run=True,
            )


class TestVerifier:
    def test_legal_directed_connection_to_gar_passes_e126(self, repo: Path) -> None:
        out = repo / "model/motivation/requirement" / f"{_REQ_ID}.outgoing.md"
        _write(out, _outgoing_md(_REQ_ID, "archimate-composition", _GAR_ID))
        registry, verifier = _deps(repo)
        codes = {i.code for i in verifier.verify_outgoing_file(out).issues}
        assert "E126" not in codes
        assert "E127" not in codes

    def test_gar_sourced_directed_connection_reports_e127(self, repo: Path) -> None:
        out = repo / "model/common/global-artifact-reference" / f"{_GAR_ID}.outgoing.md"
        _write(out, _outgoing_md(_GAR_ID, "archimate-composition", _REQ_ID))
        registry, verifier = _deps(repo)
        codes = {i.code for i in verifier.verify_outgoing_file(out).issues}
        assert "E127" in codes

    def test_gar_sourced_symmetric_connection_passes(self, repo: Path) -> None:
        out = repo / "model/common/global-artifact-reference" / f"{_GAR_ID}.outgoing.md"
        _write(out, _outgoing_md(_GAR_ID, "archimate-association", _REQ_ID))
        registry, verifier = _deps(repo)
        codes = {i.code for i in verifier.verify_outgoing_file(out).issues}
        assert "E127" not in codes
        assert "E126" not in codes
