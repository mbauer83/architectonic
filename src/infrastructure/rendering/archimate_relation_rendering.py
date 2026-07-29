from __future__ import annotations

import re
from collections.abc import Mapping, Sequence


def display_connection_label(conn_type: str) -> str:
    return conn_type.removeprefix("archimate-")


def format_specializations_guillemet(specialization_names: Sequence[str]) -> str:
    """Render specialization display names as one comma-separated guillemet stereotype, e.g.
    ``«Business Service, Audited»`` — ArchiMate §15.2's default notation for a concept
    carrying multiple specialization profiles, and ``«Name»`` for a single one. Visually
    distinct from the ``<<connection-type>>`` ASCII-bracket stereotype used for relationship
    types, so a reader can tell them apart at a glance. An empty sequence yields ``""``."""
    names = [name for name in specialization_names if name]
    return f"«{', '.join(names)}»" if names else ""


_STEREOTYPE_TOKEN_RE = re.compile(r"<<\s*([A-Za-z][A-Za-z0-9_-]*)\s*>>")
_EDGE_LABEL_RE = re.compile(r"^(?P<head>.*?)(?P<sep>\s*:\s*)(?P<label>\S.*?)\s*$")


def strip_suppressed_relation_labels(body: str, suppressed: frozenset[str]) -> str:
    """Remove redundant ``: <<reltype>>`` edge labels from an authored PUML body.

    ``suppressed`` is the set of lower-cased display label tokens whose arrow
    style already encodes the relation (``show_stereotype == False``).
    Obtain from ``DiagramTypeCatalog.suppressed_stereotype_tokens()``.
    """
    if not suppressed:
        return body
    out: list[str] = []
    for line in body.split("\n"):
        match = _EDGE_LABEL_RE.match(line)
        if match and "<<" in match.group("label"):
            def _drop(token: re.Match[str]) -> str:
                return "" if token.group(1).lower() in suppressed else token.group(0)

            new_label = _STEREOTYPE_TOKEN_RE.sub(_drop, match.group("label")).strip()
            if new_label != match.group("label"):
                head = match.group("head")
                line = head if not new_label else f"{head}{match.group('sep')}{new_label}"
        out.append(line)
    return "\n".join(out)


def format_multiplicity_label(src_multiplicity: str, tgt_multiplicity: str) -> str:
    """Return a compact multiplicity label for a connection, or '' when neither end is set."""
    has_src = bool(src_multiplicity)
    has_tgt = bool(tgt_multiplicity)
    if has_src and has_tgt:
        return f"{src_multiplicity} -> {tgt_multiplicity}"
    if has_src:
        return f"{src_multiplicity} ->"
    if has_tgt:
        return f"-> {tgt_multiplicity}"
    return ""


def format_influence_polarity(conn_type: str, attributes: Mapping[str, object]) -> str:
    """Return the colored ArchiMate influence sign declared by relationship metadata."""
    if conn_type != "archimate-influence":
        return ""
    polarity = str(attributes.get("polarity", "")).strip().lower()
    if polarity == "positive":
        return "<color:#15803d><b>+</b></color>"
    if polarity == "negative":
        return "<color:#b91c1c><b>-</b></color>"
    return ""
