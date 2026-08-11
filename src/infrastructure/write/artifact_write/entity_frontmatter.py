"""Reading one field out of an entity's frontmatter, without paying for the full parser.

Shared by the write-path checks that need an endpoint's type before anything is written — the
mediated-leg guard among them — so the read happens the same way for all of them.
"""

from __future__ import annotations

from src.application.verification.artifact_verifier import ArtifactRegistry
from src.domain.yaml_documents import parse_yaml


def entity_artifact_type(registry: ArtifactRegistry, entity_id: str) -> str | None:
    """Read artifact-type from an entity's frontmatter without importing the full parser."""

    path = registry.find_file_by_id(entity_id)
    if path is None:
        return None
    try:
        content = path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return None
        end = content.find("\n---", 3)
        if end == -1:
            return None
        fm: dict[str, object] = parse_yaml(content[3:end].strip()) or {}
        return str(fm.get("artifact-type", "")) or None
    except Exception:
        return None
