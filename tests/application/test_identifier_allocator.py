"""WU-0.3: IdentifierAllocator produces grammar-valid workspace IDs."""

from __future__ import annotations

import re

from src.application.identifier_allocator import DefaultIdentifierAllocator, IdentifierAllocator, get_default_allocator

_WORKSPACE_ID_RE = re.compile(r"^[A-Z]+@[0-9]+\.[A-Za-z0-9_-]+\..+$")


def test_default_allocator_is_protocol_instance():
    allocator = get_default_allocator()
    assert isinstance(allocator, IdentifierAllocator)


def test_allocate_produces_grammar_valid_id():
    a = DefaultIdentifierAllocator()
    id_ = a.allocate(prefix="CLF", name_hint="customer")
    assert _WORKSPACE_ID_RE.match(id_), f"ID {id_!r} does not match workspace grammar"


def test_allocate_prefix_is_used():
    a = DefaultIdentifierAllocator()
    id_ = a.allocate(prefix="CLF", name_hint="order")
    assert id_.startswith("CLF@"), f"Expected CLF@ prefix, got {id_!r}"


def test_allocate_without_name_hint():
    a = DefaultIdentifierAllocator()
    id_ = a.allocate(prefix="CLF", name_hint=None)
    assert _WORKSPACE_ID_RE.match(id_)


def test_allocate_produces_unique_ids():
    a = DefaultIdentifierAllocator()
    ids = {a.allocate(prefix="CLF", name_hint="x") for _ in range(20)}
    assert len(ids) == 20, "Allocator produced duplicate IDs"
