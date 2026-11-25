"""The test set: verdicts on held-apart stressors, and the residuality coefficient they give.

An architecture A is judged against each usable test stressor: it survives, degrades or fails. Over
the n usable stressors, with X the naive architecture's survivals and Y A's,

    R(A) = (Y − X) / n

so 0 is no better than the naive and 1 survives everything the naive did not. A *degrades* verdict
counts one half; the strict figure counts full survivals only. A figure is given only where every
usable stressor has a verdict on both A and the naive — before that, how many are judged.

A stressor a judge finds unusable (it cannot be walked, or contradicts itself) is struck, with the
reason, and leaves the denominator for every architecture. Nothing here is stored: it is read from
the verdict rows each time.

The coefficient is always shown for the integration. Where one integrated candidate holds every
other one integrated (they stack), it is the integration; where candidates were integrated apart,
none of them is, and the integration is judged as an architecture of its own, `integration`.
"""
from __future__ import annotations

import hashlib
import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any

from src.application.artifacts.document_table_rows import DocumentTables
from src.application.stress_analysis.rows import Row, in_test_set, rows_of
from src.domain.artifact_id import canonical_entity_key
from src.domain.repository.repo_default_stress_analysis import (
    DEGRADES,
    INTEGRATION_ARCHITECTURE,
    NAIVE_ARCHITECTURE,
    SURVIVES,
)
from src.domain.repository.repo_default_stress_perspectives import (
    STRESS_PERSPECTIVES,
    PerspectiveFramework,
    unwritten_perspectives,
)

#: The share of the design set a hold-out moves into the test set.
HELD_OUT_SHARE = Fraction(1, 3)


@dataclass(frozen=True)
class Verdict:
    """One judgement: what *architecture* does under test stressor *stressor*."""

    row: str
    stressor: str
    architecture: str
    verdict: str | None
    usable: bool
    reasoning: str


@dataclass(frozen=True)
class Standing:
    """How one architecture stands against the usable test stressors."""

    architecture: str
    usable: int
    survives: int
    degrades: int
    fails: int

    @property
    def judged(self) -> int:
        return self.survives + self.degrades + self.fails

    @property
    def complete(self) -> bool:
        return self.usable > 0 and self.judged == self.usable

    def survivals(self, *, strict: bool) -> Fraction:
        return Fraction(self.survives) + (0 if strict else Fraction(self.degrades, 2))


def verdicts_of(rows: Iterable[Row]) -> tuple[Verdict, ...]:
    """The survival table's rows as verdicts; a row naming no stressor or architecture says nothing."""
    return tuple(
        Verdict(row["id"], str(row["stressor"]), str(row["architecture"]), row.get("verdict") or None,
                row.get("usable") is not False, str(row.get("reasoning") or ""))
        for row in rows if row.get("stressor") and row.get("architecture")
    )


def struck(verdicts: Iterable[Verdict]) -> dict[str, str]:
    """The stressors a judge found unusable, each with the reason given."""
    return {one.stressor: one.reasoning for one in verdicts if not one.usable}


def standing_of(architecture: str, usable: Sequence[str], verdicts: Iterable[Verdict]) -> Standing:
    """*architecture*'s verdicts on the *usable* stressors; a later verdict on a stressor replaces an earlier one."""
    latest = {one.stressor: one.verdict for one in verdicts
              if one.architecture == architecture and one.verdict and one.stressor in usable}
    told = list(latest.values())
    return Standing(architecture, len(usable), told.count(SURVIVES), told.count(DEGRADES),
                    len(told) - told.count(SURVIVES) - told.count(DEGRADES))


def residuality(standing: Standing, naive: Standing, *, strict: bool = False) -> Fraction | None:
    """R = (Y − X) / n, or None until both are judged on every usable stressor."""
    if not (standing.complete and naive.complete):
        return None
    return (standing.survivals(strict=strict) - naive.survivals(strict=strict)) / standing.usable


def standing_as_read(standing: Standing, naive: Standing, *, integrated: bool) -> dict[str, Any]:
    """One architecture's line: its counts, and the coefficient beside the naive's where both are complete."""
    measured = standing.architecture != NAIVE_ARCHITECTURE
    coefficient = residuality(standing, naive) if measured else None
    strict = residuality(standing, naive, strict=True) if measured else None
    return _stated({
        "architecture": standing.architecture, "integrated": integrated,
        "usable": standing.usable, "judged": standing.judged,
        "survives": standing.survives, "degrades": standing.degrades, "fails": standing.fails,
        "naive_survives": naive.survives,
        "residuality": None if coefficient is None else float(coefficient),
        "strict": None if strict is None else float(strict),
    })


def _stated(values: dict[str, Any]) -> dict[str, Any]:
    """*values* without the keys that hold nothing: an absent figure is absent, not null, on every transport."""
    return {key: value for key, value in values.items() if value is not None}


def integration_of(integrated: Sequence[str], stack: Callable[[str], Iterable[str]]) -> str | None:
    """What stands for the integration: the integrated candidate whose *stack* holds every other one, else
    `integration` where candidates were integrated apart; None while nothing is integrated."""
    holding = [one for one in integrated if set(integrated) <= {*stack(one), one}]
    return holding[0] if holding else INTEGRATION_ARCHITECTURE if integrated else None


def evaluate(
    tables: DocumentTables, *, integrated: Sequence[str], adapted: bool, known: Sequence[str] = (),
    integration: str | None = None, frameworks: tuple[PerspectiveFramework, ...] = STRESS_PERSPECTIVES,
) -> dict[str, Any]:
    """The test set, its verdicts, every judged or integrated architecture's standing, and the procedure's stage.

    *integrated* names the candidates of the analysis integrated into the model, whose standing is
    always shown, and *integration* what stands for all of them together (`integration_of`), shown too:
    the stage counts the integration judged once it is. Without one, the integration is the last
    integrated candidate. *adapted* says whether any candidate adapts the naive architecture yet. *known* are
    the candidates that exist: a verdict naming one in either spelling of its id is read as naming it
    by the id it is stored under, so one architecture's verdicts are never counted as two. The test
    set's coverage counts the *frameworks*' perspectives.
    """
    stressors = [row for row in rows_of(tables, "stressors") if in_test_set(row)]
    held = {row["id"] for row in stressors}
    spelled = {canonical_entity_key(name): name for name in (*known, *integrated)}
    verdicts = [
        replace(one, architecture=spelled.get(canonical_entity_key(one.architecture), one.architecture))
        for one in verdicts_of(rows_of(tables, "survival")) if one.stressor in held
    ]
    unusable = struck(verdicts)
    usable = [row["id"] for row in stressors if row["id"] not in unusable]
    judged = [one.architecture for one in verdicts if one.architecture != NAIVE_ARCHITECTURE]
    together = integration or (integrated[-1] if integrated else None)
    shown = dict.fromkeys([NAIVE_ARCHITECTURE, *integrated, *([together] if together else []), *judged])
    standings = {name: standing_of(name, usable, verdicts) for name in shown}
    naive = standings[NAIVE_ARCHITECTURE]
    return {
        "stressors": [_stated({"id": row["id"], "stressor": row.get("stressor") or "", "kind": row.get("kind") or None,
                               "usable": row["id"] not in unusable, "unusable_reason": unusable.get(row["id"])})
                      for row in stressors],
        "verdicts": [_stated({"id": one.row, "stressor": one.stressor, "architecture": one.architecture,
                              "verdict": one.verdict, "usable": one.usable, "reasoning": one.reasoning})
                     for one in verdicts],
        "unwritten_perspectives": unwritten_perspectives(
            (str(row.get("kind") or "") for row in stressors), frameworks,
        ),
        "architectures": [standing_as_read(standing, naive, integrated=name in integrated)
                          for name, standing in standings.items()],
        "stage": {
            "naive_judged": naive.complete, "adapted": adapted, "integrated": bool(integrated),
            "integration_judged": together is not None and standings[together].complete,
        },
    }


def seed_for(document: str, stressors: Sequence[str]) -> int:
    """The seed of a hold-out nobody chose a seed for: the same analysis and stressors give the same one.

    Derived rather than drawn, so a dry run and the write after it, both unseeded, hold out the same
    third, and a retried write recomputes the draw it already made. The draw is a separation of the
    stressors, not a secret, so a seed anyone can recompute costs nothing.
    """
    digest = hashlib.sha256("\n".join([document, *stressors]).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % 2**31


def held_out(design: Sequence[str], seed: int) -> tuple[str, ...]:
    """A third of the *design* stressors, drawn at random from *seed*, in the document's order.

    The same stressors in the same order with the same seed draw the same third.
    """
    count = int(len(design) * HELD_OUT_SHARE)
    if count == 0:
        raise ValueError("Collect at least three design stressors before holding a third of them out.")
    chosen = set(random.Random(seed).sample(list(design), count))  # not a secret: a reproducible draw
    return tuple(ref for ref in design if ref in chosen)
