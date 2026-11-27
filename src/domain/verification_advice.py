"""Advice: the findings that may be a deliberate choice, and how an author says that it is.

An advice finding is a modelling heuristic — "this process may be a function". It never blocks a
write, a save or a promotion, and how loudly it speaks follows the status of the element it is
about: while the element is a draft it is a marker and a count, once the element is active it is
listed with its reason. An author who has considered it and chosen otherwise *acknowledges* it, with
a short reason, and the acknowledgement is stored in the element's own frontmatter:

```yaml
accepted-advice:
- code: A341
  reason: The steps run in any order; the process is a checklist.
```

An acknowledged advice is quiet at every status. Only advice can be acknowledged: a warning or an
error states something wrong, and "I accept that it is wrong" is not a reason the model can keep.

This module owns the stored shape in both directions — `accepted_advice_from_frontmatter` is the one
reading of `accepted-advice`, `accepted_advice_to_frontmatter` the one writing of it — and the
catalogue of advice codes the acknowledgement is checked against.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, NoReturn, assert_never

from src.domain.verification_findings import Issue, Severity

#: The frontmatter key an element's acknowledgements are stored under.
ACCEPTED_ADVICE_KEY: Final = "accepted-advice"

#: The longest reason an acknowledgement keeps. Short by design: it is a note beside the element, and
#: a reason that needs a page belongs in a decision record the note can name.
REASON_MAX_LENGTH: Final = 280

#: Every advice code a rule may raise, with what it says in a few words. Advice codes are `A` + three
#: digits, numbered beside the error they are nearest to (A341 sits by E340, the other rule about
#: composed parts). A code absent here cannot be acknowledged, which is what refuses warnings and
#: errors: they are never in this catalogue.
ADVICE_CODES: Final[Mapping[str, str]] = {
    "A341": "an ordered sequence whose composed parts have no order between them",
}


@dataclass(frozen=True)
class AcceptedAdvice:
    """One acknowledgement: which advice, and why the element is right as it stands."""

    code: str
    reason: str


class AdviceAcknowledgementRefused(ValueError):
    """An acknowledgement the element cannot keep: not advice, or no reason given."""


def accepted_advice_from_frontmatter(value: object) -> tuple[AcceptedAdvice, ...]:
    """The acknowledgements stored under `accepted-advice`, read tolerantly.

    Tolerant because this reads files a person may have edited: an entry that is not a mapping with
    a string `code` is skipped rather than fatal, so one malformed line never hides the others. The
    write path is where the shape is enforced (`checked_acknowledgements`).
    """
    entries = value if isinstance(value, list) else []
    return tuple(
        AcceptedAdvice(code=entry["code"].strip(), reason=str(entry.get("reason") or "").strip())
        for entry in entries
        if isinstance(entry, Mapping) and isinstance(entry.get("code"), str) and entry["code"].strip()
    )


def accepted_advice_to_frontmatter(entries: Sequence[AcceptedAdvice]) -> list[dict[str, str]]:
    """The stored form of *entries* — the inverse of `accepted_advice_from_frontmatter`."""
    return [{"code": entry.code, "reason": entry.reason} for entry in entries]


def checked_acknowledgements(value: object) -> tuple[AcceptedAdvice, ...]:
    """The acknowledgements an edit asks for, or `AdviceAcknowledgementRefused` naming why not.

    Refused: an entry that is not `{code, reason}`, a code that is not advice (a warning or an error
    code among them), an empty or overlong reason, and the same code twice.
    """
    raw = value if isinstance(value, list | tuple) else _refuse(
        "accepted_advice must be a list of {code, reason} entries"
    )
    entries = tuple(_checked_entry(item) for item in raw)
    codes = [entry.code for entry in entries]
    duplicated = sorted({code for code in codes if codes.count(code) > 1})
    return entries if not duplicated else _refuse(f"advice acknowledged more than once: {', '.join(duplicated)}")


def _checked_entry(item: object) -> AcceptedAdvice:
    if not isinstance(item, Mapping) or not isinstance(item.get("code"), str):
        return _refuse("each accepted_advice entry is a mapping with a string 'code' and a 'reason'")
    code = str(item["code"]).strip()
    reason = str(item.get("reason") or "").strip()
    if code not in ADVICE_CODES:
        return _refuse(_not_advice(code))
    if not reason:
        return _refuse(f"acknowledging {code} needs a short reason: why the element is right as it stands")
    if len(reason) > REASON_MAX_LENGTH:
        return _refuse(f"the reason for {code} is {len(reason)} characters; keep it to {REASON_MAX_LENGTH}")
    return AcceptedAdvice(code=code, reason=reason)


def _not_advice(code: str) -> str:
    kind = {"E": "an error", "W": "a warning"}.get(code[:1], "not a known advice code")
    return (
        f"{code} is {kind}: only advice can be acknowledged. A warning or an error says the content is "
        f"wrong, and is fixed rather than accepted. Advice codes: {', '.join(sorted(ADVICE_CODES))}."
    )


def _refuse(message: str) -> NoReturn:
    raise AdviceAcknowledgementRefused(message)


def acceptance_for(code: str, accepted: Iterable[AcceptedAdvice]) -> AcceptedAdvice | None:
    """The acknowledgement of *code* among *accepted*, or None."""
    return next((entry for entry in accepted if entry.code == code), None)


#: How an advice finding is presented. `marker` — a small mark on the element and a count in the
#: verify summary, no banner or toast. `listed` — named with its reason wherever findings are listed.
AdvicePresentation = Literal["marker", "listed"]


def presentation_for(status: str) -> AdvicePresentation:
    """How advice about an element of *status* is presented.

    A draft is work in progress, so its advice is a marker. An active element is what readers rely
    on, so its advice is listed. A deprecated element is on its way out and its advice is a marker
    again — listing heuristics about something being retired would only be noise. An unknown status
    is treated as active: the louder choice is the safe one for content nothing has classified.
    """
    match status:
        case "draft" | "deprecated":
            return "marker"
        case _:
            return "listed"


def advice_issue(
    code: str, message: str, *, location: str, artifact_id: str, status: str, parts: Sequence[str] = ()
) -> Issue:
    """An advice finding about one element, carrying what presentation needs to decide how loud it is."""
    if code not in ADVICE_CODES:
        raise ValueError(f"{code} is not a declared advice code")
    return Issue(
        Severity.ADVICE,
        code,
        message,
        location,
        details={"artifact_id": artifact_id, "status": status, "parts": list(parts)},
    )


def issue_status(issue: Issue) -> str:
    """The status of the element an advice finding is about, as the rule recorded it."""
    details = issue.details or {}
    return str(details.get("status", ""))


def issue_presentation(issue: Issue) -> AdvicePresentation | None:
    """How *issue* is presented if it is advice; None for an error or a warning."""
    match issue.severity:
        case "advice":
            return presentation_for(issue_status(issue))
        case "error" | "warning":
            return None
        case _:
            assert_never(issue.severity)
