"""What a verification rule reports: a severity, and one finding about one artifact.

Three severities, and they differ in what they claim. An *error* is definitional — the content
contradicts what the model says it is, and a write that introduces one is refused. A *warning* is a
claim that is wrong but not fatal. *Advice* is a modelling heuristic: the content may well be a
deliberate choice, so advice never blocks anything, is presented by the element's status, and may be
acknowledged with a reason (`verification_advice`). Kept apart from warnings so that heuristics do
not drown the findings that are simply wrong.

In the application layer until 0.7.1, which made the domain's own
`DiagramVerificationContribution` port an incomplete contract: a diagram-type module implementing
it had to reach up into the application for the vocabulary its findings are expressed in, and three
such reaches sat acknowledged in the dependency baseline. The types depend on nothing but the
standard library, so the layer they were in was the accident.

`src.application.verification.artifact_verifier_types` re-exports these, so the forty-odd modules
that import them from there are unaffected.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import reduce
from typing import Any, Final, Literal, TypeAlias, assert_never

SeverityLiteral: TypeAlias = Literal["error", "warning", "advice"]


class Severity:
    ERROR: Final[Literal["error"]] = "error"
    WARNING: Final[Literal["warning"]] = "warning"
    ADVICE: Final[Literal["advice"]] = "advice"


#: The letter every rule code of each severity begins with: `E340`, `W307`, `A341`. One statement of
#: the code shape, which the verifier's code register and the acknowledgement check both read.
CODE_PREFIX: Final[Mapping[SeverityLiteral, str]] = {"error": "E", "warning": "W", "advice": "A"}

#: A rule code of any severity: its severity's letter and three digits.
RULE_CODE: Final = re.compile(rf"\A[{''.join(CODE_PREFIX.values())}]\d{{3}}\Z")


def severity_of_code(code: str) -> SeverityLiteral | None:
    """The severity a rule code's letter declares, or None for a string that is not a rule code."""
    if not RULE_CODE.match(code):
        return None
    return next((severity for severity, prefix in CODE_PREFIX.items() if code.startswith(prefix)), None)


@dataclass(frozen=True)
class SeverityCounts:
    """How many findings of each severity — the one place findings are tallied by severity."""

    errors: int = 0
    warnings: int = 0
    advice: int = 0

    def counting(self, severity: SeverityLiteral) -> SeverityCounts:
        """These counts with one more finding of *severity*. Exhaustive: a fourth severity fails here."""
        match severity:
            case "error":
                return SeverityCounts(self.errors + 1, self.warnings, self.advice)
            case "warning":
                return SeverityCounts(self.errors, self.warnings + 1, self.advice)
            case "advice":
                return SeverityCounts(self.errors, self.warnings, self.advice + 1)
            case _:
                assert_never(severity)


def count_severities(severities: Iterable[SeverityLiteral]) -> SeverityCounts:
    """Tally *severities* into a `SeverityCounts`."""
    return reduce(SeverityCounts.counting, severities, SeverityCounts())


@dataclass(frozen=True)
class Issue:
    severity: SeverityLiteral
    code: str
    message: str
    location: str
    details: Mapping[str, Any] | None = None
    actions: tuple[Mapping[str, Any], ...] | None = None
