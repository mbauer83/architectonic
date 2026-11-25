"""Give every diagram grouping an id, and re-key every edge label by the relation it labels.

Two identities a diagram's statements now carry, and what this step does for a diagram written
before they existed:

* **A grouping's id.** Each ``authored-groupings`` entry gains a stable ``id``, derived from the
  diagram and the entry's place and label — so two checkouts of one repository upgraded apart mint
  the same identity, and a later write through the tools mints nothing different.
* **A drawn relation's key.** ``edge-labels`` was keyed ``SRC_ALIAS:TGT_ALIAS``, which cannot tell
  two relations between one pair apart. Each such key becomes the key of the one relation the
  diagram draws between those two aliases.

**It does not guess.** A pair that two of the diagram's relations fit, or none, or whose aliases
cannot be resolved from what the diagram itself states, is reported for a person to settle, with the
candidates named, and left exactly as it is. An alias is resolved the way the product assigns one —
from the element's id, a further occurrence numbered in the order stated, a held element by the
alias its row states — never from another file, so the answer cannot depend on what else a checkout
happens to hold.

Only the two blocks are rewritten, each re-dumped with the options the diagram writer dumps with;
every other byte of the file — any field this step has no opinion about, an uncommitted edit — is
left as it was. Applying it twice changes nothing the second time.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.application.artifacts.parsing import extract_yaml_block
from src.application.modeling.diagram_identities import alias_by_instance, drawn_relation_ends, strings_of
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.steps._frontmatter_blocks import with_block
from src.application.repository_upgrade.steps._frontmatter_scan import list_frontmatter_candidate_files
from src.domain.artifact_id import stable_id
from src.domain.diagrams.authored_groupings import GROUPING_ID_KEY, walk_groupings, with_grouping_ids
from src.domain.diagrams.relation_key import alias_pair_of
from src.domain.repository.frontmatter import (
    Frontmatter,
    opens_with_frontmatter,
    read_frontmatter,
    replace_frontmatter_text,
)
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding

_GROUPINGS = "authored-groupings"
_EDGE_LABELS = "edge-labels"


@dataclass(frozen=True)
class _Rekeying:
    """What becomes of one diagram's alias-pair keys: those with one relation to name, and the rest."""

    settled: Mapping[str, str] = field(default_factory=dict)
    #: The key, and the relation keys that fit it — several, or none.
    unsettled: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


def _rekeying(frontmatter: Mapping[str, object]) -> _Rekeying:
    labels = frontmatter.get(_EDGE_LABELS)
    retired = [str(key) for key in labels if alias_pair_of(str(key))] if isinstance(labels, Mapping) else []
    if not retired:
        return _Rekeying()
    aliases = alias_by_instance(frontmatter)
    drawn = {
        key: (aliases.get(stable_id(source), aliases.get(source)), aliases.get(stable_id(target), aliases.get(target)))
        for key, (source, target) in drawn_relation_ends(
            strings_of(frontmatter.get("connection-ids-used")),
            frontmatter.get("diagram-entities"),
            frontmatter.get("connections"),
            frontmatter.get("bindings"),
        ).items()
    }
    settled: dict[str, str] = {}
    unsettled: dict[str, tuple[str, ...]] = {}
    for key in retired:
        pair = alias_pair_of(key)
        assert pair is not None
        as_drawn = [relation for relation, ends in drawn.items() if ends == pair]
        # A notation may draw a relation against its direction; the pair then reads the other way.
        fitting = as_drawn or [relation for relation, ends in drawn.items() if ends == pair[::-1]]
        if len(fitting) == 1 and fitting[0] not in settled.values():
            settled[key] = fitting[0]
        else:
            unsettled[key] = tuple(fitting)
    return _Rekeying(settled, unsettled)


def _unidentified(frontmatter: Mapping[str, object]) -> int:
    return sum(1 for _trail, entry in walk_groupings(frontmatter.get(_GROUPINGS)) if not entry.get(GROUPING_ID_KEY))


class DiagramIdentityKeysStep:
    id = "d12-grouping-ids-and-drawn-relation-keys"
    version = 1
    description = "Give each diagram grouping a stable id and re-key edge labels by the relation they label"
    scanned_surface: ScannedSurface = "diagram_frontmatter"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        findings: list[UpgradeFinding] = []
        for rel in list_frontmatter_candidate_files(view):
            frontmatter = self._diagram_frontmatter(view.read_text(rel))
            if frontmatter is None:
                continue
            if count := _unidentified(frontmatter):
                findings.append(UpgradeFinding(
                    step_id=self.id, finding_id=f"grouping-without-id:{rel}", location=rel,
                    description=f"{count} grouping(s) have no id of their own",
                    severity="warning", auto_migratable=True,
                    rewrite_summary=f"assign a stable id to {count} grouping(s)",
                ))
            rekeying = _rekeying(frontmatter)
            if rekeying.settled:
                findings.append(UpgradeFinding(
                    step_id=self.id, finding_id=f"edge-label-keyed-by-alias-pair:{rel}", location=rel,
                    description=f"{len(rekeying.settled)} edge label(s) are keyed by an alias pair",
                    severity="warning", auto_migratable=True,
                    rewrite_summary=f"re-key {len(rekeying.settled)} edge label(s) by the relation each labels",
                ))
            findings.extend(self._unsettled(rel, key, fitting) for key, fitting in rekeying.unsettled.items())
        return findings

    def _unsettled(self, rel: str, key: str, fitting: tuple[str, ...]) -> UpgradeFinding:
        if fitting:
            why = f"fits {len(fitting)} relations this diagram draws"
            how = "Re-state the label under the one it belongs to: " + " | ".join(fitting)
        else:
            why = "fits no relation this diagram draws that its own statements can resolve"
            how = "Re-state the label under the key of the relation it belongs to (its connection id), or remove it"
        return UpgradeFinding(
            step_id=self.id, finding_id=f"edge-label-not-settled:{rel}:{key}", location=rel,
            description=f"edge label '{key}' is keyed by an alias pair that {why}",
            severity="warning", auto_migratable=False,
            manual_instructions=f"{how}, with artifact_edit_diagram(edge_labels=…).",
        )

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        rewritten: dict[str, bool] = {}
        for location in dict.fromkeys(finding.location for finding in findings):
            content = view.read_text(location)
            updated = self._rewritten(content) if content is not None else None
            rewritten[location] = updated is not None
            if updated is not None and updated != content:
                writer.write_text(location, updated)
        return [
            AppliedFinding(finding=finding, outcome="applied")
            if rewritten[finding.location]
            else AppliedFinding(finding=finding, outcome="error", detail="file no longer holds a diagram")
            for finding in findings
        ]

    def _diagram_frontmatter(self, content: str | None) -> dict[str, object] | None:
        if content is None or not opens_with_frontmatter(content):
            return None
        frontmatter = extract_yaml_block(content)
        if not isinstance(frontmatter, dict) or str(frontmatter.get("artifact-type", "")) != "diagram":
            return None
        return frontmatter

    def _rewritten(self, content: str) -> str | None:
        frontmatter = self._diagram_frontmatter(content)
        reading = read_frontmatter(content)
        if frontmatter is None or not isinstance(reading, Frontmatter):
            return None
        text = reading.text
        if _unidentified(frontmatter):
            groupings = frontmatter.get(_GROUPINGS)
            identified = with_grouping_ids(
                groupings if isinstance(groupings, list) else [],
                diagram_id=stable_id(str(frontmatter.get("artifact-id", ""))),
            )
            text = with_block(text, _GROUPINGS, identified)
        settled = _rekeying(frontmatter).settled
        labels = frontmatter.get(_EDGE_LABELS)
        if settled and isinstance(labels, Mapping):
            text = with_block(text, _EDGE_LABELS, {settled.get(str(key), key): label for key, label in labels.items()})
        return replace_frontmatter_text(content, text)
