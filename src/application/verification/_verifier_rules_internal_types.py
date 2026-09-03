"""Which rule verifies which system-managed entity type.

Internal types are system-managed: created by an operation, never authored directly, and kept out of
user-facing entity lists. That they share a *class* does not mean they share a *shape* — a global
artifact reference names a promoted artifact, a proposed change names a reference and carries an
edit — so the verifier dispatches on the type rather than running one type's rule over all of them.

A mapping rather than a chain of comparisons: a third internal type is a row, and a type with no row
is verified by the rules every entity gets and nothing more, which is the correct default for one
that declares no extra fields.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from src.application.global_reference_endpoints import GLOBAL_ARTIFACT_REFERENCE_TYPE
from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE
from src.application.verification._verifier_rules_grf import check_global_artifact_reference
from src.application.verification._verifier_rules_proposed_change import check_proposed_change
from src.application.verification.artifact_verifier_types import VerificationResult

if TYPE_CHECKING:
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry


#: What every internal-type rule takes: the frontmatter, the index, and where to report.
InternalTypeRule = Callable[[dict, "ArtifactRegistry | None", VerificationResult, str], None]

_RULES: Mapping[str, InternalTypeRule] = {
    GLOBAL_ARTIFACT_REFERENCE_TYPE: check_global_artifact_reference,
    PROPOSED_CHANGE_TYPE: check_proposed_change,
}


def check_internal_entity(
    fm: dict,
    registry: "ArtifactRegistry | None",
    result: VerificationResult,
    loc: str,
) -> None:
    """Run the rule for this internal type, if it has one."""
    rule = _RULES.get(str(fm.get("artifact-type", "")))
    if rule is not None:
        rule(fm, registry, result, loc)
