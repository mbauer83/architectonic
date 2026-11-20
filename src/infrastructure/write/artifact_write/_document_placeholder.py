"""Document placeholder-body generation for ``document.create_document``.

Split out of ``document.py`` to keep its CRUD/write-path functions the
cohesive unit; these are pure functions over a doc-type schema's sections.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

from src.application.artifacts.document_schema import (
    REQUIRED_CONNECTIONS_KEY,
    SUGGESTED_CONNECTIONS_KEY,
    get_document_schema_object,
)
from src.application.artifacts.document_tables import TableSpec

_PLACEHOLDER = "<!-- Add content here -->"


def _validate_section_templates(
    section_templates: object,
    required_sections: list[str],
    doc_type: str,
) -> None:
    if not isinstance(section_templates, dict):
        raise ValueError(
            f"Doc-type {doc_type!r}: section_templates must be an object, "
            f"got {type(section_templates).__name__}"
        )
    valid_sections = set(required_sections)
    for key, value in section_templates.items():
        if key not in valid_sections:
            raise ValueError(
                f"Doc-type {doc_type!r}: section_templates key {key!r} is not in "
                f"required_sections {required_sections}"
            )
        if not isinstance(value, str):
            raise ValueError(
                f"Doc-type {doc_type!r}: section_templates[{key!r}] must be a string, "
                f"got {type(value).__name__}"
            )


def _declared_tables(repo_root: Path, doc_type: str) -> dict[str, tuple[TableSpec, ...]]:
    """The typed tables each section of `doc_type` declares, by section name."""
    schema = get_document_schema_object(repo_root, doc_type)
    return {section.name: section.tables for section in schema.sections} if schema else {}


def _starter(template_body: str | None, *, holds_a_table: bool) -> str:
    if template_body is not None:
        return template_body.rstrip()
    return "" if holds_a_table else _PLACEHOLDER


def _build_placeholder_body(
    required_sections: list[object],
    section_templates: dict[str, str] | None = None,
    tables: Mapping[str, Sequence[TableSpec]] | None = None,
) -> str:
    """A body with every section the type declares: its starter text, then each table it declares.

    A section that declares a table is given the table's header and no placeholder comment — the
    empty table is what there is to fill in.
    """
    parts = []
    declared = tables or {}
    templates = section_templates or {}
    for section in required_sections:
        if isinstance(section, dict):
            section_name = str(section.get("name") or "").strip()
            template_value = section.get("template")
            template_body = str(template_value) if template_value is not None else None
            hint = _section_expected_link_hint(section)
        else:
            section_name = str(section)
            template_body = templates.get(section_name)
            hint = ""
        if not section_name:
            continue
        scaffolds = [table.scaffold() for table in declared.get(section_name, ())]
        starter = _starter(template_body, holds_a_table=bool(scaffolds))
        blocks = "\n\n".join(block for block in (starter, *scaffolds) if block)
        parts.append(f"## {section_name}\n\n{hint}{blocks}\n")
    return "\n".join(parts)


def _section_expected_link_hint(section: dict) -> str:
    required = _string_list(section.get(REQUIRED_CONNECTIONS_KEY))
    suggested = _string_list(section.get(SUGGESTED_CONNECTIONS_KEY))
    parts = []
    if required:
        parts.append(f"required: {', '.join(required)}")
    if suggested:
        parts.append(f"suggested: {', '.join(suggested)}")
    if not parts:
        return ""
    return f"<!-- Expected links for this section: {'; '.join(parts)} -->\n"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
