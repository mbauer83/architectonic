"""Tests for artifact record types — immutability contract (WU-13)."""

from __future__ import annotations

import typing
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

import pytest

from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
)


def _entity(**kw) -> EntityRecord:
    defaults = dict(
        artifact_id="ENT@001",
        artifact_type="app-service",
        name="My Service",
        version="1.0",
        status="draft",
        domain="application",
        subdomain="app-service",
        path=Path("/fake/entity.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="My Service",
        display_alias="",
    )
    defaults.update(kw)
    return EntityRecord(**defaults)


def _connection(**kw) -> ConnectionRecord:
    defaults = dict(
        artifact_id="CON@001",
        source="ENT@001",
        target="ENT@002",
        conn_type="archimate-association",
        version="1.0",
        status="draft",
        path=Path("/fake/conn.md"),
        extra={},
        content_text="",
    )
    defaults.update(kw)
    return ConnectionRecord(**defaults)


def _diagram(**kw) -> DiagramRecord:
    defaults = dict(
        artifact_id="DIA@001",
        artifact_type="architecture-diagram",
        name="My Diagram",
        diagram_type="arch",
        version="1.0",
        status="draft",
        path=Path("/fake/diagram.md"),
        extra={},
    )
    defaults.update(kw)
    return DiagramRecord(**defaults)


def _document(**kw) -> DocumentRecord:
    defaults = dict(
        artifact_id="DOC@001",
        doc_type="decision",
        title="My Doc",
        status="draft",
        path=Path("/fake/doc.md"),
        keywords=(),
        sections=(),
        content_text="",
        extra={},
    )
    defaults.update(kw)
    return DocumentRecord(**defaults)


class TestEntityRecordImmutability:
    def test_extra_annotation_is_mapping(self) -> None:
        hints = typing.get_type_hints(EntityRecord)
        # Must be Mapping, not dict
        assert hints["extra"] is not dict
        origin = getattr(hints["extra"], "__origin__", None)
        assert origin is Mapping

    def test_display_blocks_annotation_is_mapping(self) -> None:
        hints = typing.get_type_hints(EntityRecord)
        assert hints["display_blocks"] is not dict
        origin = getattr(hints["display_blocks"], "__origin__", None)
        assert origin is Mapping

    def test_accepts_mapping_proxy_for_extra(self) -> None:
        proxy = MappingProxyType({"key": "val"})
        rec = _entity(extra=proxy)
        assert rec.extra["key"] == "val"

    def test_accepts_mapping_proxy_for_display_blocks(self) -> None:
        proxy = MappingProxyType({"archimate": "```yaml\nname: X\n```"})
        rec = _entity(display_blocks=proxy)
        assert rec.display_blocks["archimate"].startswith("```yaml")

    def test_extra_reads_work(self) -> None:
        rec = _entity(extra={"x": 1, "y": [1, 2, 3]})
        assert rec.extra.get("x") == 1
        assert rec.extra.get("missing") is None

    def test_display_blocks_reads_work(self) -> None:
        rec = _entity(display_blocks={"archimate": "content"})
        assert rec.display_blocks.get("archimate") == "content"

    def test_frozen_prevents_field_reassignment(self) -> None:
        rec = _entity(extra={"a": 1})
        with pytest.raises((AttributeError, TypeError)):
            rec.extra = {"b": 2}  # type: ignore[misc]


class TestConnectionRecordImmutability:
    def test_extra_annotation_is_mapping(self) -> None:
        hints = typing.get_type_hints(ConnectionRecord)
        origin = getattr(hints["extra"], "__origin__", None)
        assert origin is Mapping

    def test_accepts_mapping_proxy_for_extra(self) -> None:
        proxy = MappingProxyType({"ref": "abc"})
        rec = _connection(extra=proxy)
        assert rec.extra["ref"] == "abc"


class TestDiagramRecordImmutability:
    def test_extra_annotation_is_mapping(self) -> None:
        hints = typing.get_type_hints(DiagramRecord)
        origin = getattr(hints["extra"], "__origin__", None)
        assert origin is Mapping

    def test_accepts_mapping_proxy_for_extra(self) -> None:
        proxy = MappingProxyType({"diagram-entities": []})
        rec = _diagram(extra=proxy)
        assert rec.extra.get("diagram-entities") == []


class TestDocumentRecordImmutability:
    def test_extra_annotation_is_mapping(self) -> None:
        hints = typing.get_type_hints(DocumentRecord)
        origin = getattr(hints["extra"], "__origin__", None)
        assert origin is Mapping

    def test_accepts_mapping_proxy_for_extra(self) -> None:
        proxy = MappingProxyType({"custom-field": "value"})
        rec = _document(extra=proxy)
        assert rec.extra.get("custom-field") == "value"
