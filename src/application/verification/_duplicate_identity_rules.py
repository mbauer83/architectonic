"""E319 — two artifacts claiming one rename-stable identity.

Identity is the ``PREFIX@epoch.random`` stem, and everything downstream trusts that: references
resolve by it, renames cascade by it, and the reading lens, the diagram reconcile and the reference
healer all key on it. Two files carrying the same stem are two artifacts claiming one identity, so a
reference spelled with it resolves to whichever the index happened to key first — silently, and
possibly differently after a reindex.

**The condition was already fail-closed, in one place only.** `assert_no_duplicate_short_ids` aborts
backend startup over exactly this. It says nothing to an author working through MCP, who never
restarts anything: a rename that left the old file in place ran for a day with `artifact_verify`
reporting 0 errors and 0 warnings, while the backend would have refused to serve the same content.
A repository that verifies clean and cannot be served is the disagreement this closes.

**Read from the candidate's own records, not from the index scan.** `scan_duplicate_short_ids` walks
files on disk and is what startup uses; a verification contribution is asked about the *transaction*,
where the answer has to include what this write is about to add. Records also carry the spellings,
which is what an author needs in order to know which file to remove.

An error, and the usual reason to soften does not apply. The recent activity diagnostics describe
content authored in good faith that still renders correctly; this describes two files that cannot both
be right, on a condition the product's own startup already refuses to proceed past. A warning here
would leave the verifier and the backend disagreeing about whether the repository is usable.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from src.domain.artifact_id import stable_id
from src.domain.repository.artifact_location import artifact_kind_declared_at
from src.domain.verification_findings import Issue, Severity


def _spellings_by_stem(records: Any) -> dict[str, list[str]]:
    """Every distinct file-backed id, grouped by the identity it claims.

    Distinct, because one artifact reached by two routes is not a duplicated identity: a candidate
    transaction overlays the committed view, so the same record can be listed twice, and reporting
    that would make every write report itself.

    **File-backed only.** A diagram-only element is identified *within* its diagram — its id is the
    diagram's own with a compartment appended — so it shares the diagram's stem by construction, and
    counting it made every diagram that draws one report itself as a duplicate of itself. That is not
    a near-miss: this rule is about two files claiming one identity, and such an element has no file.
    `host_diagram_id` is what says so, and it is the same marker the workspace-identity rule reads.
    """
    by_stem: dict[str, set[str]] = defaultdict(set)
    for record in records:
        artifact_id = getattr(record, "artifact_id", "")
        if artifact_id and not getattr(record, "host_diagram_id", None):
            by_stem[stable_id(artifact_id)].add(artifact_id)
    return {stem: sorted(ids) for stem, ids in by_stem.items() if len(ids) > 1}


class DuplicateStableIdContribution:
    """E319: more than one artifact carrying one rename-stable id."""

    diagnostic_codes: tuple[str, ...] = ("E319",)

    def run(self, ctx: Any, result: Any) -> None:
        records = [*ctx.candidate.list_entities(), *ctx.candidate.list_diagrams()]
        for stem, spellings in sorted(_spellings_by_stem(records).items()):
            result.issues.append(duplicate_finding(stem, spellings, ctx.location))


def duplicate_finding(stem: str, spellings: list[str], location: str) -> Issue:
    return Issue(Severity.ERROR, "E319", f"{len(spellings)} artifacts claim the identity '{stem}': "
                 f"{', '.join(spellings)}. Keep one and remove the duplicate.", location)


def duplicate_kind_files(root: Path, paths: Iterable[Path]) -> Iterator[tuple[Path, Issue]]:
    """Find distinct files claiming one stable identity for kinds that declare their own prefix."""
    claims: dict[str, set[Path]] = defaultdict(set)
    for path in paths:
        kind = artifact_kind_declared_at(path.relative_to(root))
        if kind is not None and kind.id_prefix is not None:
            claims[stable_id(kind.file_identity(path))].add(path)
    for stem, files in sorted(claims.items()):
        if len(files) > 1:
            first, *others = sorted(files)
            yield first, duplicate_finding(stem, [str(p.relative_to(root)) for p in (first, *others)], str(first))
