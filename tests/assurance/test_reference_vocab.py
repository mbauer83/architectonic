"""Tests for the reference vocabulary loader."""

from __future__ import annotations

from src.infrastructure.assurance.reference_vocab import list_schemes, load_scheme, validate_classification


def test_bundled_schemes_available() -> None:
    schemes = list_schemes()
    assert "STRIDE" in schemes
    assert "ISO26262" in schemes
    assert "ISO21434" in schemes


def test_validate_stride_code() -> None:
    result = validate_classification("STRIDE", "S")
    assert result["valid"] is True
    assert result["scheme"] == "STRIDE"
    assert result["code"] == "S"
    assert "label" in result


def test_validate_stride_all_codes() -> None:
    for code in ["S", "T", "R", "I", "D", "E"]:
        result = validate_classification("STRIDE", code)
        assert result["valid"] is True, f"STRIDE:{code} should be valid"


def test_validate_unknown_stride_code() -> None:
    result = validate_classification("STRIDE", "X")
    assert result["valid"] is False
    assert "reason" in result


def test_validate_unknown_scheme_is_free_form() -> None:
    result = validate_classification("ATT&CK", "T1059")
    assert result["valid"] is True
    assert result.get("free_form") is True


def test_validate_iso26262_clause() -> None:
    result = validate_classification("ISO26262", "6-8")
    assert result["valid"] is True


def test_load_stride_scheme() -> None:
    data = load_scheme("STRIDE")
    assert data
    assert data.get("scheme") == "STRIDE"
    assert "codes" in data


def test_load_iso26262_scheme() -> None:
    data = load_scheme("ISO26262")
    assert data
    assert "integrity_levels" in data or "key_clauses" in data
