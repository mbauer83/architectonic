"""Verifier tests for datatype generalization_set consistency (E339)."""

from pathlib import Path

from src.application.verification.artifact_verifier_types import VerificationResult
from src.diagram_types.datatype._contributions_keys import GENERALIZATION_SET_CONTRIBUTION
from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext


def _run(*, sets, connections) -> list:
    fm = {
        "diagram-type": "datatype",
        "diagram-entities": {
            "classifier": [{"id": "g"}, {"id": "g2"}, {"id": "card"}, {"id": "pp"}],
            "generalization_set": sets,
        },
        "connections": connections,
    }
    ctx = BaseDiagramVerificationContext(
        fm=fm, loc="test.puml", scope="engagement", diagram_id="DT-A",
        allowed_connections=frozenset(), allowed_entities=frozenset(), catalogs=None,
    )
    result = VerificationResult(path=Path("test.puml"), file_type="diagram")
    GENERALIZATION_SET_CONTRIBUTION.run(None, ctx, result)
    return [i for i in result.issues if i.code == "E339"]


def _gen(source, target, set_id):
    return {"id": f"{source}->{target}", "conn_type": "dt-generalization",
            "source": source, "target": target, "generalization_set": set_id}


_SET = [{"id": "GS@1.x.m", "label": "method", "is_covering": True, "is_disjoint": True}]


def test_consistent_set_passes() -> None:
    conns = [_gen("card", "g", "GS@1.x.m"), _gen("pp", "g", "GS@1.x.m")]
    assert _run(sets=_SET, connections=conns) == []


def test_unknown_set_reference_emits_e339() -> None:
    conns = [_gen("card", "g", "GS@missing")]
    issues = _run(sets=_SET, connections=conns)
    assert len(issues) == 1
    assert "unknown" in issues[0].message


def test_differing_general_ends_emit_e339() -> None:
    conns = [_gen("card", "g", "GS@1.x.m"), _gen("pp", "g2", "GS@1.x.m")]
    issues = _run(sets=_SET, connections=conns)
    assert len(issues) == 1
    assert "differing" in issues[0].message


def test_e339_registered() -> None:
    from src.diagram_types.datatype import module

    codes = {
        code
        for contribution in module.diagram_verification_contributions()
        for code in contribution.diagnostic_codes
    }
    assert "E339" in codes
