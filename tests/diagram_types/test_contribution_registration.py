"""WU-0.8 acceptance: E330/E331 registered as DiagramVerificationContribution.

Verifies that:
- The datatype module registers a contribution with diagnostic_codes ("E330","E331").
- Calling the contribution's run() with a known E330-triggering frontmatter emits E330.
- Existing E330/E331 logic is preserved (parity).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification.artifact_verifier_types import Severity, VerificationResult
from src.diagram_types.datatype import module as datatype_module
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry


@pytest.fixture(scope="module")
def catalogs():
    return build_runtime_catalogs(get_module_registry())


def _result() -> VerificationResult:
    return VerificationResult(path=Path("diag.puml"), file_type="diagram")


_DOB_A = "DOB@111.aaaa.alpha"
_DOB_B = "DOB@222.bbbb.beta"


def _fm_e330_trigger():
    """Frontmatter that should trigger E330: dt-association with DOB-bound classifiers, no backing."""
    return {
        "diagram-type": "datatype",
        "diagram-entities": {
            "classifier": [
                {"id": "cls_a", "classifier_kind": "class"},
                {"id": "cls_b", "classifier_kind": "class"},
            ]
        },
        "connections": [
            {"id": "c1", "conn_type": "dt-association", "source": "cls_a", "target": "cls_b"}
        ],
        "bindings": [
            {
                "id": "b_a",
                "subject": {"kind": "entity", "id": "cls_a"},
                "correspondence_kind": "represents",
                "target": {"entity_id": _DOB_A},
            },
            {
                "id": "b_b",
                "subject": {"kind": "entity", "id": "cls_b"},
                "correspondence_kind": "represents",
                "target": {"entity_id": _DOB_B},
            },
        ],
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.verifies("REQ@1781976357.A5WgC8")
def test_datatype_module_has_backing_contribution() -> None:
    """Datatype module exposes a contribution with diagnostic_codes == ('E330','E331')."""
    contribs = datatype_module.diagram_verification_contributions()
    codes = {c: c.diagnostic_codes for c in contribs}
    matching = [c for c in contribs if set(c.diagnostic_codes) == {"E330", "E331"}]
    assert matching, (
        f"Expected a contribution with diagnostic_codes ('E330','E331') but got: {codes}"
    )


def test_backing_contribution_e330_parity(catalogs) -> None:
    """Calling contribution.run() with an E330-triggering fm emits the E330 issue (parity)."""
    contribs = datatype_module.diagram_verification_contributions()
    e330_contrib = next(c for c in contribs if "E330" in c.diagnostic_codes)

    from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext  # noqa: PLC0415

    fm = _fm_e330_trigger()
    ctx = BaseDiagramVerificationContext(
        fm=fm,
        loc="diag.puml",
        scope="engagement",
        diagram_id="DT-test",
        allowed_connections=frozenset({f"{_DOB_A}---{_DOB_B}@@archimate-association"}),
        allowed_entities=frozenset(),
        catalogs=catalogs,
    )

    result = _result()

    class _NullRepo:
        def get_entity(self, a): return None
        def get_diagram(self, a): return None
        def list_entities(self, **kw): return []
        def list_diagrams(self, **kw): return []
        def scope_for_path(self, p): return "engagement"

    e330_contrib.run(_NullRepo(), ctx, result)

    e330_issues = [i for i in result.issues if i.code == "E330"]
    assert e330_issues, f"Expected E330 issue but got: {[i.code for i in result.issues]}"
    assert e330_issues[0].severity == Severity.ERROR
