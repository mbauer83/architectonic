"""Loader for document-type schemata from .arch-repo/documents/."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.domain.repository.repo_layout import ARCH_DOC_SCHEMATA, ARCH_REPO

#: What a document or a section declares it should reach. One list per severity, holding terms from
#: any of the three vocabularies — see `src.application.artifacts.reference_terms`, which owns
#: reading them. The entity-only spelling below is what these were called while entity types were
#: the only vocabulary; it is still accepted so no schema file has to be rewritten, normalised here
#: so there is one declaration reader, and never emitted again.
REQUIRED_CONNECTIONS_KEY = "required_connections"
SUGGESTED_CONNECTIONS_KEY = "suggested_connections"
LEGACY_REQUIRED_CONNECTIONS_KEY = "required_entity_type_connections"
LEGACY_SUGGESTED_CONNECTIONS_KEY = "suggested_entity_type_connections"


@dataclass(frozen=True)
class SectionSpec:
    name: str
    template: str | None = None
    required_connections: tuple[str, ...] = ()
    suggested_connections: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name}
        if self.template is not None:
            result["template"] = self.template
        if self.required_connections:
            result[REQUIRED_CONNECTIONS_KEY] = list(self.required_connections)
        if self.suggested_connections:
            result[SUGGESTED_CONNECTIONS_KEY] = list(self.suggested_connections)
        return result


@dataclass(frozen=True)
class DocumentSchema:
    doc_type: str
    data: dict[str, Any]
    sections: tuple[SectionSpec, ...]
    required_connections: tuple[str, ...] = ()
    suggested_connections: tuple[str, ...] = ()

    @property
    def required_sections(self) -> tuple[str, ...]:
        return tuple(section.name for section in self.sections)

    @property
    def section_templates(self) -> dict[str, str]:
        return {
            section.name: section.template
            for section in self.sections
            if section.template is not None
        }

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.data)
        result["sections"] = [section.to_dict() for section in self.sections]
        result["required_sections"] = list(self.required_sections)
        if self.section_templates:
            result["section_templates"] = self.section_templates
        else:
            result.pop("section_templates", None)
        result.pop(LEGACY_REQUIRED_CONNECTIONS_KEY, None)
        result.pop(LEGACY_SUGGESTED_CONNECTIONS_KEY, None)
        for key, terms in (
            (REQUIRED_CONNECTIONS_KEY, self.required_connections),
            (SUGGESTED_CONNECTIONS_KEY, self.suggested_connections),
        ):
            if terms:
                result[key] = list(terms)
            else:
                result.pop(key, None)
        return result


def normalize_document_schema(doc_type: str, raw: dict[str, Any]) -> DocumentSchema:
    return DocumentSchema(
        doc_type=doc_type,
        data=dict(raw),
        sections=_normalize_sections(doc_type, raw),
        required_connections=_connection_terms(raw, REQUIRED_CONNECTIONS_KEY, LEGACY_REQUIRED_CONNECTIONS_KEY),
        suggested_connections=_connection_terms(raw, SUGGESTED_CONNECTIONS_KEY, LEGACY_SUGGESTED_CONNECTIONS_KEY),
    )


def _connection_terms(raw: dict[str, Any], key: str, legacy_key: str) -> tuple[str, ...]:
    """The declared terms under either spelling, in declaration order and without repeats.

    Both keys are read rather than one winning, because a schema part-way through being rewritten
    would otherwise silently lose whichever list it kept in the old spelling.
    """
    seen: dict[str, None] = {}
    for candidate in (key, legacy_key):
        for term in _string_tuple(raw.get(candidate)):
            seen.setdefault(term, None)
    return tuple(seen)


def _normalize_sections(doc_type: str, raw: dict[str, Any]) -> tuple[SectionSpec, ...]:
    sections_raw = raw.get("sections")
    if sections_raw is not None:
        if not isinstance(sections_raw, list):
            raise ValueError(f"Doc-type {doc_type!r}: sections must be a list")
        return tuple(_section_from_raw(doc_type, item) for item in sections_raw if isinstance(item, dict))

    required_sections: list[object] = raw.get("required_sections") or []
    if not isinstance(required_sections, list):
        raise ValueError(f"Doc-type {doc_type!r}: required_sections must be a list")
    templates: dict[object, object] = raw.get("section_templates") or {}
    if not isinstance(templates, dict):
        raise ValueError(f"Doc-type {doc_type!r}: section_templates must be an object")
    valid_sections = {str(name) for name in required_sections}
    for key in templates:
        if str(key) not in valid_sections:
            raise ValueError(
                f"Doc-type {doc_type!r}: section_templates key {str(key)!r} is not in "
                f"required_sections {[str(name) for name in required_sections]}"
            )
    return tuple(
        SectionSpec(
            name=str(name),
            template=str(templates[name]) if name in templates and templates[name] is not None else None,
        )
        for name in required_sections
    )


def _section_from_raw(doc_type: str, raw: dict[str, Any]) -> SectionSpec:
    name = str(raw.get("name") or "").strip()
    if not name:
        raise ValueError(f"Doc-type {doc_type!r}: section entries require a non-empty name")
    template = raw.get("template")
    return SectionSpec(
        name=name,
        template=str(template) if template is not None else None,
        required_connections=_connection_terms(raw, REQUIRED_CONNECTIONS_KEY, LEGACY_REQUIRED_CONNECTIONS_KEY),
        suggested_connections=_connection_terms(raw, SUGGESTED_CONNECTIONS_KEY, LEGACY_SUGGESTED_CONNECTIONS_KEY),
    )


def _string_tuple(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw)


@lru_cache(maxsize=4)
def load_document_schemata(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Return {doc_type: schema_dict} for all .arch-repo/documents/*.json files."""
    schemata_dir = repo_root / ARCH_REPO / ARCH_DOC_SCHEMATA
    if not schemata_dir.exists():
        return {}
    result: dict[str, dict[str, Any]] = {}
    for schema_file in sorted(schemata_dir.glob("*.json")):
        try:
            data = json.loads(schema_file.read_text(encoding="utf-8"))
            result[schema_file.stem] = normalize_document_schema(schema_file.stem, data).to_dict()
        except (json.JSONDecodeError, OSError):
            pass
    return result


@lru_cache(maxsize=4)
def load_document_schema_objects(repo_root: Path) -> dict[str, DocumentSchema]:
    """Return {doc_type: normalized DocumentSchema} for all document schema files."""
    return {
        doc_type: normalize_document_schema(doc_type, schema)
        for doc_type, schema in load_document_schemata(repo_root).items()
    }


def get_document_schema(repo_root: Path, doc_type: str) -> dict[str, Any] | None:
    return load_document_schemata(repo_root).get(doc_type)


def get_document_schema_object(repo_root: Path, doc_type: str) -> DocumentSchema | None:
    return load_document_schema_objects(repo_root).get(doc_type)


def get_document_subdirectory(schema: dict, doc_type: str) -> str:
    raw = str(schema.get("subdirectory") or doc_type).strip().replace("\\", "/")
    parts = [part for part in raw.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"Invalid document subdirectory for doc-type {doc_type!r}: {raw!r}")
    return "/".join(parts)
