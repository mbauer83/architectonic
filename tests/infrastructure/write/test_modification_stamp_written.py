"""A written artifact records *when* it was written, to the second, in UTC.

A date-only stamp cannot order two edits made on the same day — which is precisely what the
browse lists' "last modified" column has to do — so the write path stamps a full UTC instant.
Pinning the clock makes the assertion exact rather than a shape check.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.application.artifacts.parsing import extract_yaml_block
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.clock import frozen_now
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.boundary import modification_stamp
from src.infrastructure.write.artifact_write.entity import create_entity

_FROZEN = "2026-07-24T09:15:00Z"
_CANONICAL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _engagement_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-STAMP" / "architecture-repository"
    (root / ".arch-repo").mkdir(parents=True)
    return root


def _verifier(repo_root: Path) -> ArtifactVerifier:
    registry = ArtifactRegistry(shared_artifact_index([repo_root]))
    return ArtifactVerifier(registry, catalogs=build_runtime_catalogs(get_module_registry()))


def test_modification_stamp_is_a_canonical_utc_instant() -> None:
    assert _CANONICAL.match(modification_stamp())


def test_modification_stamp_reads_the_central_clock() -> None:
    with frozen_now(_FROZEN):
        assert modification_stamp() == _FROZEN


def test_created_entity_records_the_instant_it_was_written(tmp_path: Path) -> None:
    repo_root = _engagement_root(tmp_path)
    verifier = _verifier(repo_root)

    with frozen_now(_FROZEN):
        result = create_entity(
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            artifact_type="requirement",
            name="Stamped Requirement",
            summary="A requirement written at a known instant.",
            properties=None,
            notes=None,
            artifact_id=None,
            version="0.1.0",
            status="draft",
            last_updated=None,
            dry_run=False,
        )

    frontmatter = extract_yaml_block(Path(result.path).read_text(encoding="utf-8"))
    assert frontmatter is not None
    # Quoted in YAML, so it round-trips as the canonical string rather than a date object.
    assert frontmatter["last-updated"] == _FROZEN
