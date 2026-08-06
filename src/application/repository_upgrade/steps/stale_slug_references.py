"""Heal references naming an artifact by a slug it no longer has.

A rename now cascades: every file naming the renamed entity is rewritten in the same transaction,
and the verifier reports what is left (W121 on a connection endpoint, W305/W306 on a diagram). A
repository written by an older version has neither — its renames touched the entity's own file and
stopped — so it carries references spelled with titles their artifacts dropped long ago.

Nothing is broken by that, which is exactly why it needs a step rather than a warning to live with:
identity is the ``PREFIX@epoch.random`` stem, so a stale reference resolves correctly forever and no
read ever fails. The cost is entirely on the reader — the slug is the only part of an id a human
interprets, and one naming a former title misleads in review — so drift accumulates silently and is
never repaired by use.

Matching is on the stem, never on a particular old spelling, for the reason the rename cascade
matches that way: a reference missed once holds some third slug, and a fix keyed to the previous
spelling can no longer find it. Keyed on the stem, a reference is healed however stale it is, and
the rewrite is the cascade's own one-line rule (``full_ids_with_stem(stem).sub(current, text)``)
rather than a second copy of it that could drift.

Composite connection ids need no separate handling: they are two entity ids joined by ``---``, the
pattern is bounded so a match stops at that join, and rewriting each endpoint yields the current
composite. That is also why the pattern must stay the shared one — a looser slug charset swallows
the separator and the prefix after it.
"""

from __future__ import annotations

from src.application.repository_upgrade.canonical_ids import canonical_index
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.steps._frontmatter_scan import list_frontmatter_candidate_files
from src.domain.artifact_id import current_spelling_of, full_ids_with_stem, stable_id
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding


def _stale_spellings(text: str, canonical: dict[str, set[str]]) -> dict[str, str]:
    """Stale spelling → current spelling, for every reference in *text*. Empty when it is current."""
    rewrites: dict[str, str] = {}
    for stem, candidates in canonical.items():
        if len(candidates) != 1:
            # Ambiguous across tiers: there is no single current spelling to rewrite to, and
            # guessing would retitle a correct reference. The resolver diagnoses that on its own.
            continue
        for reference in full_ids_with_stem(stem).findall(text):
            current = current_spelling_of(reference, canonical)
            if current is not None:
                rewrites[reference] = current
    return rewrites


class StaleSlugReferenceStep:
    id = "d10-stale-slug-references"
    version = 1
    description = "Rewrite references naming an artifact by a slug it no longer has"
    scanned_surface: ScannedSurface = "diagram_frontmatter"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        files = list_frontmatter_candidate_files(view)
        canonical = canonical_index([view])
        if not canonical:
            return []
        findings: list[UpgradeFinding] = []
        for rel in files:
            content = view.read_text(rel)
            if content is None:
                continue
            rewrites = _stale_spellings(content, canonical)
            if not rewrites:
                continue
            plural = "" if len(rewrites) == 1 else "s"
            named = ", ".join(f"{stale} -> {current}" for stale, current in sorted(rewrites.items())[:3])
            findings.append(
                UpgradeFinding(
                    step_id=self.id,
                    finding_id=f"stale-slug:{rel}",
                    location=rel,
                    description=f"{len(rewrites)} reference{plural} name an artifact by a former slug",
                    severity="warning",
                    auto_migratable=True,
                    rewrite_summary=f"respell {len(rewrites)} reference{plural} ({named})",
                )
            )
        return findings

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        canonical = canonical_index([view])
        outcomes: list[AppliedFinding] = []
        for finding in findings:
            content = view.read_text(finding.location)
            if content is None:
                outcomes.append(AppliedFinding(finding=finding, outcome="error", detail="file no longer exists"))
                continue
            rewritten = content
            for stale, current in _stale_spellings(content, canonical).items():
                rewritten = full_ids_with_stem(stable_id(stale)).sub(current, rewritten)
            if rewritten == content:
                # Detection re-derives from content, so nothing to do means an earlier run did it.
                outcomes.append(AppliedFinding(finding=finding, outcome="skipped", detail="already current"))
                continue
            writer.write_text(finding.location, rewritten)
            outcomes.append(AppliedFinding(finding=finding, outcome="applied"))
        return outcomes
