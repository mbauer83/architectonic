"""The assurance verifier's issue and result types.

Separate from both the rules and the orchestration so a rule module can construct an issue
without importing the runner that will call it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.application.verification.assurance_findings import AssuranceFindingKind, SeverityLiteral


@dataclass(frozen=True)
class AssuranceIssue:
    severity: SeverityLiteral
    code: str
    message: str
    node_id: str = ""
    witness: tuple[str, ...] = ()
    """The relationships or facts the finding rests on, where it rests on any.

    Carried rather than folded into the message because a finding about the architecture graph asks
    someone to act on a claim they did not make. "This element is load-bearing" is not checkable;
    the relationships that make it so are. Empty for the rules whose subject is the store itself,
    where the reader can already see what the finding is about.
    """

    subject_name: str = ""
    """The subject's reader-facing name, where the finding's source can supply one.

    A finding identified only by artifact id is a finding nobody acts on: a hundred of them read as
    a wall of `REQ@1777369067.3cJ1Yi`. Empty when the architecture model cannot describe the
    subject, which is honest — the id is then all there is.
    """

    @classmethod
    def of(
        cls,
        kind: AssuranceFindingKind,
        *,
        message: str,
        node_id: str = "",
        witness: tuple[str, ...] = (),
        subject_name: str = "",
    ) -> AssuranceIssue:
        """Build an issue from its catalogued kind, so code and severity are never restated."""
        return cls(
            severity=kind.severity, code=kind.code, message=message, node_id=node_id,
            witness=witness, subject_name=subject_name,
        )


@dataclass
class AssuranceVerificationResult:
    issues: list[AssuranceIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def errors(self) -> list[AssuranceIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[AssuranceIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def informational(self) -> list[AssuranceIssue]:
        """Coverage statements. Counted separately so a gate on errors and warnings stays meaningful
        while the statements still reach a reader."""
        return [i for i in self.issues if i.severity == "info"]
