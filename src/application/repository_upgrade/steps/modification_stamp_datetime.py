"""Upgrade the `last-updated` frontmatter stamp from a date to a full UTC datetime.

Repositories written before the stamp gained a time component carry `last-updated: '2026-01-01'`.
A date-only stamp cannot order two changes made on the same day, which is exactly what a
"last modified" column has to do, so the persisted form is now `YYYY-MM-DDTHH:MM:SSZ`.

Two properties this step must have, and how it gets them:

* **The historic value survives.** A date-only stamp becomes midnight UTC *on that date* —
  never "now". Re-stamping would destroy the only record of when the artifact last changed.
* **Nothing else in the file moves.** Only the value token on the top-level `last-updated:`
  line is replaced, in place: key order, quote style elsewhere, comments, and body content
  stay byte-for-byte identical. Reparsing and re-dumping the frontmatter would be simpler
  and would silently reorder keys.

A stamp that already reads back as a canonical UTC instant is left alone, which is what makes
a second run a no-op. A stamp no date parser can make sense of is reported for a human rather
than guessed at.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from src.application.artifacts.parsing import extract_yaml_block
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.steps._frontmatter_scan import list_frontmatter_candidate_files
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding

_STAMP_KEY = "last-updated"
_CANONICAL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_FRONTMATTER_BLOCK_RE = re.compile(r"^(---\n)(.*?)(\n---\n)", re.DOTALL)
# Top-level only (no leading indent): a nested `last-updated:` inside another mapping is not
# the artifact's own stamp and is not this step's business.
_STAMP_LINE_RE = re.compile(
    rf"^(?P<prefix>{_STAMP_KEY}:[ \t]*)(?P<value>[^#\n]*?)(?P<suffix>[ \t]*(?:#[^\n]*)?)$",
    re.MULTILINE,
)


def canonical_utc_stamp(value: object) -> str | None:
    """Return *value* as ``YYYY-MM-DDTHH:MM:SSZ``, or None if it is not a recognisable instant.

    Accepts what YAML can produce for a timestamp scalar — a `datetime`, a `date`, or the
    string forms of either — because whether a stamp was quoted decides which of those the
    parser hands back. A naive datetime is read as UTC: the writer only ever emitted UTC.
    """
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, date):
        return f"{value.isoformat()}T00:00:00Z"
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if _CANONICAL_RE.match(text):
        return text
    try:
        return canonical_utc_stamp(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        pass
    try:
        return canonical_utc_stamp(date.fromisoformat(text))
    except ValueError:
        return None


def _reads_back_canonical(value: object) -> bool:
    """True when the parsed stamp is already a canonical UTC instant — nothing to migrate.

    An *unquoted* canonical datetime parses to a `datetime`, which qualifies: the read path
    normalizes it to the identical string, so rewriting it would change bytes without
    changing meaning.
    """
    if isinstance(value, datetime):
        return True
    return isinstance(value, str) and bool(_CANONICAL_RE.match(value.strip()))


class ModificationStampDatetimeStep:
    id = "modification-stamp-datetime"
    version = 1
    description = f"Upgrade date-only '{_STAMP_KEY}' stamps to full UTC datetimes"
    scanned_surface: ScannedSurface = "modification_stamps"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        findings: list[UpgradeFinding] = []
        for rel in list_frontmatter_candidate_files(view):
            content = view.read_text(rel)
            if content is None or not content.startswith("---"):
                continue
            frontmatter = extract_yaml_block(content)
            if not isinstance(frontmatter, dict) or _STAMP_KEY not in frontmatter:
                continue
            raw = frontmatter[_STAMP_KEY]
            if _reads_back_canonical(raw):
                continue
            upgraded = canonical_utc_stamp(raw)
            if upgraded is None:
                findings.append(
                    UpgradeFinding(
                        step_id=self.id,
                        finding_id=f"unreadable-modification-stamp:{rel}",
                        location=rel,
                        description=f"'{_STAMP_KEY}' value {raw!r} is not a recognisable date or instant",
                        severity="warning",
                        auto_migratable=False,
                        manual_instructions=(
                            f"Set '{_STAMP_KEY}' to a quoted UTC instant "
                            "('YYYY-MM-DDTHH:MM:SSZ'), or remove the field to leave the "
                            "artifact unstamped. It is left untouched until then."
                        ),
                    )
                )
                continue
            findings.append(
                UpgradeFinding(
                    step_id=self.id,
                    finding_id=f"date-only-modification-stamp:{rel}",
                    location=rel,
                    description=f"'{_STAMP_KEY}' has no time component ({raw!s})",
                    severity="info",
                    auto_migratable=True,
                    rewrite_summary=f"'{_STAMP_KEY}' {raw!s} -> '{upgraded}' (same date, midnight UTC)",
                )
            )
        return findings

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        outcomes: list[AppliedFinding] = []
        for finding in findings:
            content = view.read_text(finding.location)
            if content is None:
                outcomes.append(AppliedFinding(finding=finding, outcome="error", detail="file no longer exists"))
                continue
            rewritten = rewrite_modification_stamp(content)
            if rewritten is None:
                outcomes.append(
                    AppliedFinding(finding=finding, outcome="skipped", detail=f"no top-level '{_STAMP_KEY}' line")
                )
                continue
            writer.write_text(finding.location, rewritten)
            outcomes.append(AppliedFinding(finding=finding, outcome="applied"))
        return outcomes


def rewrite_modification_stamp(content: str) -> str | None:
    """Return *content* with its frontmatter stamp canonicalized, or None if there is nothing
    to rewrite (no frontmatter, no top-level stamp line, or an unreadable value)."""
    block = _FRONTMATTER_BLOCK_RE.match(content)
    if block is None:
        return None
    yaml_text = block.group(2)
    line = _STAMP_LINE_RE.search(yaml_text)
    if line is None:
        return None
    upgraded = canonical_utc_stamp(line.group("value").strip().strip("'\""))
    if upgraded is None:
        return None
    rewritten_line = f"{line.group('prefix')}'{upgraded}'{line.group('suffix')}"
    rewritten_yaml = yaml_text[: line.start()] + rewritten_line + yaml_text[line.end() :]
    return content[: block.start(2)] + rewritten_yaml + content[block.end(2) :]
