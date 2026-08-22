"""What a `format` facet decides — the rule, as the procedure that decides it.

A `format` on an attribute says the value *addresses* something rather than merely matching a shape
(see `profiles.ProfileAttribute.format`). This module is where each format's rule is specified: the
alternatives a value may satisfy, one predicate each, any of them sufficing.

**Why the specification is here and not beside the checker that runs it.** A shipped attribute
description told authors that `format: uri` was "informative only" and that "the validator runs no
format checker, so any string is accepted", months after the checker had begun refusing values — so
nineteen values written in good faith were reported invalid by a checker whose own schema had
promised the author that anything would do. The description and the checker were two statements of
one rule, in two layers, free to drift. Now there is one rule, and both the description an author
reads and the message a refusal gives are **derived from it**: neither can say something the
procedure does not do.

Each alternative carries the term this project calls it by. A term is the rule's vocabulary — the
name of a form a value may take — not prose about the rule; the sentences are composed by whoever
needs a sentence, from these terms.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date

#: An absolute reference: `https://…`, `ssh://…`, `mailto:…`. A scheme is letters, digits and
#: `+ - .` after a letter, per RFC 3986 §3.1.
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")

#: `git@github.com:owner/repo.git` — the SCP-like address a git remote is usually written as. It is
#: **not** a URI: it has no scheme, and `github.com` cannot be one because a scheme may not contain
#: `@`. It is what people paste into a source-repository field, so it is accepted as its own form
#: rather than by an accident of laxness.
_SCP_SSH_ADDRESS = re.compile(r"^[^\s/@]+@[^\s/@]+:")

#: `date` is a calendar date, `YYYY-MM-DD`, per RFC 3339 full-date — the shape a review date or a
#: decision date is written in everywhere else in this project.
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_repository_relative_path(value: str) -> bool:
    """A path to something this repository manages, written as every other link to it is.

    Recognised by carrying a separator or an extension, which is what distinguishes `notes.md` from
    a bare word — the first version of this rule asked only that the value hold no whitespace, and
    so accepted `askJohn` as readily as a link.
    """
    return "/" in value or "." in value


def _is_calendar_date(value: str) -> bool:
    if _ISO_DATE.match(value) is None:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class AcceptedForm:
    """One alternative a format admits: the term for it, and the predicate that decides it."""

    term: str
    admits: Callable[[str], bool]


@dataclass(frozen=True)
class FormatRule:
    """A format facet's specification. A value satisfies it by satisfying any one of its forms."""

    forms: tuple[AcceptedForm, ...]

    def admits(self, value: str) -> bool:
        """Whether *value* satisfies this format.

        Whitespace disqualifies every form of every rule: a value that addresses something has none,
        and a calendar date has none either. Stated once here rather than in each predicate.
        """
        candidate = value.strip()
        if not candidate or any(character.isspace() for character in candidate):
            return False
        return any(form.admits(candidate) for form in self.forms)

    @property
    def terms(self) -> tuple[str, ...]:
        return tuple(form.term for form in self.forms)


#: Every format a declaration may name. `_startup_schema_policy` refuses any other, because a format
#: nothing checks would compile into the schema and be enforced by nothing.
FORMAT_RULES: Mapping[str, FormatRule] = {
    "uri": FormatRule((
        AcceptedForm("an absolute reference carrying a scheme", lambda v: bool(_URI_SCHEME.match(v))),
        AcceptedForm(
            "an SCP-like SSH address, as a git remote is usually written",
            lambda v: bool(_SCP_SSH_ADDRESS.match(v)),
        ),
        AcceptedForm("a relative path to something this repository manages", _is_repository_relative_path),
    )),
    "date": FormatRule((AcceptedForm("an ISO date, written YYYY-MM-DD", _is_calendar_date),)),
}

ENFORCED_FORMATS: frozenset[str] = frozenset(FORMAT_RULES)


def accepted_forms_phrase(format_name: str) -> str:
    """This format's terms as one phrase, or empty where no rule specifies the format.

    The one place a sentence about a format is assembled, so a description and a refusal message are
    the same claim worded for two audiences rather than two claims.
    """
    rule = FORMAT_RULES.get(format_name)
    if rule is None:
        return ""
    terms = list(rule.terms)
    return f"{', '.join(terms[:-1])}, or {terms[-1]}" if len(terms) > 1 else terms[0]
