"""How a document file is spelled, read apart and found.

Split out of ``document.py`` so that module is the three writes — create, edit, delete — and this
one is what they share: the frontmatter block as every document write spells it, the file split
into its frontmatter and body, the references section, and the lookup of a document by its id.
"""

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.domain.artifact_id import stable_id
from src.domain.repository.frontmatter import Frontmatter, FrontmatterProblem, read_frontmatter
from src.domain.yaml_documents import parse_yaml


class DocumentNotFoundError(ValueError):
    """The addressed document does not exist.

    A ``ValueError`` subclass, following ``GroupOpError`` and ``SaveVerificationError``, so every
    existing ``except ValueError`` caller — the MCP write tools among them — keeps working unchanged
    while a caller that cares can tell "you named a document that is not there" from "this payload is
    malformed". The distinction is a status code: the first is 404 and the second 400, and both were
    a non-disclosing 500 while this was a bare ``ValueError`` that no route caught.
    """


def _dump_yaml_text(data: object) -> str:
    dumped = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    if not isinstance(dumped, str):
        raise TypeError("yaml.dump returned non-string output")
    return dumped.rstrip()


def _document_frontmatter_yaml(
    *,
    artifact_id: str,
    doc_type: str,
    title: str,
    status: str,
    version: str,
    last_updated: str,
    keywords: list[str] | None,
    extra_frontmatter: dict[str, object] | None,
) -> str:
    """A document's frontmatter block as every document write spells it, fences excluded."""
    fm: dict[str, object] = {
        "artifact-id": artifact_id,
        "artifact-type": "document",
        "doc-type": doc_type,
        "title": title,
        "status": status,
        "version": version,
        "last-updated": last_updated,
    }
    if keywords:
        fm["keywords"] = keywords
    if extra_frontmatter:
        fm.update({k: v for k, v in extra_frontmatter.items() if k not in fm})
    return _dump_yaml_text(fm)


def _format_document_markdown(*, body: str, **frontmatter: Any) -> str:
    return f"---\n{_document_frontmatter_yaml(**frontmatter)}\n---\n\n{body.strip()}\n"


def _verification_to_document_dict(path: Path, res) -> dict[str, object]:
    return {
        "path": str(path),
        "file_type": "document",
        "valid": res.valid,
        "issues": [
            {"severity": i.severity, "code": i.code, "message": i.message, "location": i.location} for i in res.issues
        ],
    }


#: The heading a one-way reference is recorded under. One name, so `references_to_entity` finds the
#: links and a reader finds the section — a document that referenced the model from wherever the
#: prose happened to mention it would be a document nobody could audit.
REFERENCES_HEADING = "References"


def render_references(document_path: Path, entity_paths: list[Path]) -> str:
    """A `## References` section of relative markdown links, or nothing when there are none.

    Relative to the document, because that is how a reference is *read*: `references_to_entity`
    resolves `document.parent / href`, and the same link works in any markdown viewer without the
    repository being served from anywhere in particular.

    References run **document → model, one way** (ADR@1783406789). The model is not edited to record
    that a document mentions it, which is what keeps a document a commentary on the model rather
    than a second place the model is defined.
    """
    if not entity_paths:
        return ""
    import os  # noqa: PLC0415 — one relpath, not worth a module-level import for every caller

    rows = [
        f"- [{path.stem}]({os.path.relpath(path, document_path.parent).replace(os.sep, '/')})"
        for path in sorted(entity_paths)
    ]
    return f"\n\n## {REFERENCES_HEADING}\n\n" + "\n".join(rows) + "\n"


_MANAGED_DOC_FM_KEYS = frozenset(
    {"artifact-id", "artifact-type", "doc-type", "title", "status", "version", "last-updated", "keywords"}
)


def _split_document_frontmatter(raw: str, path: Path) -> tuple[dict[str, object], str]:
    """Split a document's raw text into its parsed frontmatter mapping and body."""
    reading = read_frontmatter(raw)
    if reading is FrontmatterProblem.NO_OPENING_FENCE:
        raise ValueError(f"Document at {path} has no YAML frontmatter")
    if not isinstance(reading, Frontmatter):
        raise ValueError(f"Document at {path} has malformed YAML frontmatter")
    parsed = parse_yaml(reading.text)
    fm: dict[str, object] = parsed if isinstance(parsed, dict) else {}
    return fm, reading.body.lstrip("\n")


def _resolve_document_path(docs_root: Path, artifact_id: str) -> Path | None:
    """Locate a document by filename stem (the artifact id), group subdirectory included.

    Documents have no registry-backed lookup, so this mirrors
    ``diagram_delete._find_diagram_file``'s own disk-scan short-id tolerance: an exact
    filename match wins; otherwise a short (rename-stable) id is accepted if exactly one
    file matches it (ambiguous short ids report not-found, same fail-safe convention as
    ``_MemStore.canonical_id``).
    """
    if not docs_root.exists():
        return None
    short = stable_id(artifact_id)
    short_matches: list[Path] = []
    for path in docs_root.rglob("*.md"):
        if path.stem == artifact_id:
            return path
        if stable_id(path.stem) == short:
            short_matches.append(path)
    return short_matches[0] if len(short_matches) == 1 else None
