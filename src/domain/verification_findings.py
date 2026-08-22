"""What a verification rule reports: a severity, and one finding about one artifact.

In the application layer until 0.7.1, which made the domain's own
`DiagramVerificationContribution` port an incomplete contract: a diagram-type module implementing
it had to reach up into the application for the vocabulary its findings are expressed in, and three
such reaches sat acknowledged in the dependency baseline. The types depend on nothing but the
standard library, so the layer they were in was the accident.

`src.application.verification.artifact_verifier_types` re-exports these, so the forty-odd modules
that import them from there are unaffected.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal, TypeAlias

SeverityLiteral: TypeAlias = Literal["error", "warning"]


class Severity:
    ERROR: Final[Literal["error"]] = "error"
    WARNING: Final[Literal["warning"]] = "warning"


@dataclass(frozen=True)
class Issue:
    severity: SeverityLiteral
    code: str
    message: str
    location: str
    details: Mapping[str, Any] | None = None
    actions: tuple[Mapping[str, Any], ...] | None = None
