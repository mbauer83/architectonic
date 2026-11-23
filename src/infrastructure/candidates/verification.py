"""File and reference rules for a candidate; standing is checked against current model fields."""
from pathlib import Path

from src.application.change_sets.candidate_recorded_form import load_candidate
from src.application.change_sets.stacking import sets_beneath, stack_of
from src.application.change_sets.standing import standing_of
from src.application.verification._verifier_snapshot import RepositorySnapshot
from src.application.verification.artifact_verifier_parsing import read_file
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.application.verification.kind_verification import PerKindVerification
from src.infrastructure.candidates.reads import live_reading
from src.infrastructure.candidates.repository import KIND, CandidateRepository

RULE_CODES = frozenset({"E001", "E104", "E420", "W421"})


def verify_candidate(host: PerKindVerification, path: Path, snapshot: RepositorySnapshot | None) -> VerificationResult:
    result = VerificationResult(path, KIND.name)
    if (text := read_file(path, result, str(path), snapshot=snapshot)) is None:
        return result
    try:
        candidate = load_candidate(text)
        store = CandidateRepository(path.parent.parent)
        store.path(candidate.id)
        if KIND.file_identity(path) != candidate.id:
            result.issues.append(Issue(Severity.ERROR, "E104", "Candidate id differs from its file name.", str(path)))
        stack = stack_of(candidate, store.find)
        if host.registry is not None:
            live = live_reading(stack, host.registry)
            for ref in candidate.scope:
                if ref not in live.entities:
                    raise ValueError(f"Scoped model entity {ref!r} is unavailable.")
            for item in standing_of(candidate.changes, live, beneath=sets_beneath(stack)):
                if item.standing in {"drifted", "conflicting"}:
                    result.issues.append(Issue(Severity.WARNING, "W421", item.reason, str(path)))
    except (ValueError, OSError) as exc:
        result.issues.append(Issue(Severity.ERROR, "E420", str(exc), str(path)))
    return result
