"""MCP/REST surface acceptance for the datatype diagram type.

Verifies:
  1. The assurance MCP surface (src/infrastructure/mcp/assurance_mcp/) has no
     static import dependency on src.diagram_types.datatype — the two surfaces
     are orthogonal by design.
  2. The datatype consistency check is a strict no-op for non-datatype diagrams
     (belt-and-suspenders beyond TestNonDatatypeDiagram in test_datatype_backing_rules).
  3. Issue.details + actions survive the as_issue_dict / as_verification_result_dict
     serializers that back both MCP and REST responses.
     (Detailed serialization tests live in test_issue_diagnostic_contract.py;
     this test adds a datatype-specific payload round-trip.)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.application.verification._verifier_rules_datatype import check_datatype_backing_consistency
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.mcp.artifact_mcp.formatting import as_issue_dict, as_verification_result_dict

_ASSURANCE_MCP_ROOT = Path(__file__).parents[3] / "src/infrastructure/mcp/assurance_mcp"

# ---------------------------------------------------------------------------
# 1. Assurance MCP surface isolation
# ---------------------------------------------------------------------------

_DATATYPE_IMPORT_PATTERNS = (
    "src.diagram_types.datatype",
    "from src.diagram_types.datatype",
    "diagram_types.datatype",
)


def _static_imports(py_file: Path) -> list[str]:
    """Return all import module names found in a Python source file via AST."""
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def test_assurance_mcp_surface_has_no_datatype_import():
    """No file in the assurance MCP surface may import from the datatype module."""
    offenders = []
    for py_file in sorted(_ASSURANCE_MCP_ROOT.rglob("*.py")):
        for imp in _static_imports(py_file):
            if "diagram_types.datatype" in imp or "datatype" in imp.split(".")[-1:]:
                if any(pat in imp for pat in ("diagram_types.datatype",)):
                    offenders.append((py_file.name, imp))
    assert not offenders, (
        f"Assurance MCP files must not import from src.diagram_types.datatype: {offenders}"
    )


# ---------------------------------------------------------------------------
# 2. Consistency check is a no-op for assurance diagrams
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def catalogs():
    return build_runtime_catalogs(get_module_registry())


_ASSURANCE_DIAGRAM_TYPES = ("control-structure", "bowtie", "gsn", "uca-matrix")


@pytest.mark.parametrize("dtype", _ASSURANCE_DIAGRAM_TYPES)
def test_backing_consistency_no_op_for_assurance_diagrams(dtype, catalogs):
    fm = {
        "diagram-type": dtype,
        "connections": [
            {"id": "c1", "conn_type": "dt-association", "source": "cls_a", "target": "cls_b"}
        ],
        "bindings": [
            {"id": "b1", "subject": {"kind": "entity", "id": "cls_a"}, "target": {"entity_id": "DOB@1"}},
            {"id": "b2", "subject": {"kind": "entity", "id": "cls_b"}, "target": {"entity_id": "DOB@2"}},
        ],
    }
    result = VerificationResult(path=Path("diag.puml"), file_type="diagram")
    check_datatype_backing_consistency(fm, set(), catalogs.ontology, catalogs.diagram_types, result, "x")
    assert not result.issues, (
        f"check_datatype_backing_consistency emitted issues for diagram-type='{dtype}'"
    )


# ---------------------------------------------------------------------------
# 3. Datatype-specific Issue payload round-trips through MCP serializers
# ---------------------------------------------------------------------------


def _e330_issue() -> Issue:
    return Issue(
        severity=Severity.ERROR,
        code="E330",
        message="dt-* edge 'e1' (dt-association) has no backing connection",
        location="diag.puml",
        details={
            "dob_source": "DOB@1.a",
            "dob_target": "DOB@2.b",
            "dt_conn_id": "e1",
            "dt_relationship_kind": "association",
            "permitted_backing_kinds": ["association"],
            "preferred_default": "archimate-association",
        },
        actions=({"type": "create_connection", "connection_type": "archimate-association",
                  "source": "DOB@1.a", "target": "DOB@2.b"},),
    )


class TestIssuePayloadRoundTrip:
    def test_e330_details_survive_as_issue_dict(self):
        d = as_issue_dict(_e330_issue())
        assert d["code"] == "E330"
        assert d["details"]["dob_source"] == "DOB@1.a"
        assert d["details"]["permitted_backing_kinds"] == ["association"]
        assert d["details"]["preferred_default"] == "archimate-association"

    def test_e330_actions_survive_as_issue_dict(self):
        d = as_issue_dict(_e330_issue())
        assert isinstance(d["actions"], list)
        act = d["actions"][0]
        assert act["type"] == "create_connection"
        assert act["connection_type"] == "archimate-association"
        assert act["source"] == "DOB@1.a"
        assert act["target"] == "DOB@2.b"

    def test_e330_survives_as_verification_result_dict(self):
        result = VerificationResult(path=Path("diag.puml"), file_type="diagram")
        result.issues.append(_e330_issue())
        d = as_verification_result_dict(result)
        issues = d["issues"]
        assert len(issues) == 1
        assert issues[0]["code"] == "E330"
        assert "details" in issues[0]
        assert "actions" in issues[0]
