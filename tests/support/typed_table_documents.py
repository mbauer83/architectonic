"""Two document types that declare typed tables, and the means to write a document of one.

Fixtures and not shipped types: a stress analysis (stressors, end states, adaptations, the incidence
of a stressor on a component) and an architecture evaluation (ATAM's utility tree and approach
analysis). They exist to hold the table declaration to two real shapes.

Rows are written here through the same owners the product reads them with — the table owner for the
row, the typed-property codec for a value, the declaration for a list of row ids — so a test that
writes a row and reads it back is a round trip over those owners and not over a spelling of its own.
"""

from __future__ import annotations

import json
import os.path
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.application.artifacts.document_schema import DocumentSchema, normalize_document_schema
from src.application.artifacts.document_tables import TableSpec
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.markdown_table import escape_cell, format_row

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "document_types"

STRESS_ANALYSIS = "stress-analysis"
ARCHITECTURE_EVALUATION = "architecture-evaluation"
EXAMPLE_TYPES = (STRESS_ANALYSIS, ARCHITECTURE_EVALUATION)


def raw_document_type(doc_type: str) -> dict[str, Any]:
    raw: dict[str, Any] = json.loads((_FIXTURES / f"{doc_type}.json").read_text(encoding="utf-8"))
    return raw


def document_type(doc_type: str) -> DocumentSchema:
    return normalize_document_schema(doc_type, raw_document_type(doc_type))


def table_of(schema: DocumentSchema, name: str) -> TableSpec:
    return next(table for section in schema.sections for table in section.tables if table.name == name)


@lru_cache(maxsize=1)
def runtime_catalogs() -> RuntimeCatalogs:
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


def repository_in(tmp_path: Path, *doc_types: str) -> Path:
    """An engagement repository declaring `doc_types`, and `adr` for a document to link."""
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    schemata = repo / ".arch-repo" / "documents"
    schemata.mkdir(parents=True)
    for doc_type in doc_types:
        (schemata / f"{doc_type}.json").write_text(json.dumps(raw_document_type(doc_type)), encoding="utf-8")
    (schemata / "adr.json").write_text(json.dumps({"abbreviation": "ADR", "sections": []}), encoding="utf-8")
    return repo


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def entity_in(repo: Path, artifact_type: str, slug: str) -> Path:
    """An entity file of `artifact_type`, with as much frontmatter as a link to it is read by."""
    artifact_id = f"ENT@1000000001.{slug[:6]}.{slug}"
    return _write(
        repo / "model" / artifact_type / f"{artifact_id}.md",
        f"---\nartifact-id: {artifact_id}\nartifact-type: {artifact_type}\nname: {slug}\n---\n\n## {slug}\n",
    )


def adr_in(repo: Path, slug: str) -> Path:
    artifact_id = f"ADR@1000000002.{slug[:6]}.{slug}"
    return _write(
        repo / "docs" / "adr" / f"{artifact_id}.md",
        f"---\nartifact-id: {artifact_id}\nartifact-type: document\ndoc-type: adr\ntitle: {slug}\n"
        "status: draft\n---\n",
    )


def document_path(repo: Path, schema: DocumentSchema) -> Path:
    return repo / "docs" / str(schema.data["subdirectory"]) / f"{schema.data['abbreviation']}@1000000003.Doc.doc.md"


def link_to(target: Path, *, written_in: Path, label: str = "it") -> str:
    """A markdown link to `target` as a document at `written_in` spells it."""
    return f"[{label}]({Path(os.path.relpath(target, written_in.parent)).as_posix()})"


def table_text(spec: TableSpec, rows: Sequence[Mapping[str, str]] = (), *, row_ids: Sequence[str] = ()) -> str:
    """The table with `rows`: each a column name → the cell as spelled. Ids count from one unless given."""
    ids = row_ids or [spec.row_id(number) for number in range(1, len(rows) + 1)]
    lines = [
        format_row([escape_cell(row_id), *(row.get(column.name, "") for column in spec.columns)])
        for row_id, row in zip(ids, rows, strict=True)
    ]
    return "\n".join([spec.scaffold(), *lines])


def document_text(schema: DocumentSchema, tables: Mapping[str, str], **frontmatter: str) -> str:
    """A document of `schema` holding every declared section, and `tables` by table name.

    A declared table not given is written empty.
    """
    fields = {"title": "A document", "status": "draft"} | frontmatter
    head = "".join(f"{key}: {value}\n" for key, value in fields.items())
    sections = [
        "\n\n".join([f"## {section.name}", *(tables.get(table.name, table.scaffold()) for table in section.tables)])
        for section in schema.sections
    ]
    return (
        f"---\nartifact-id: DOC@1000000003.Doc.doc\nartifact-type: document\ndoc-type: {schema.doc_type}\n"
        f"{head}---\n\n" + "\n\n".join(sections) + "\n"
    )
