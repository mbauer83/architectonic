"""Who authored a node, and which analyses draw on it.

Two different facts about one node, and a reader who cannot tell them apart cannot tell a native
finding from a borrowed one:

* **Authorship** is `assurance_nodes.analysis_id` — single-valued, fixed, the analysis that
  produced the node. It is what the FMEA's own failure modes have and what a control-structure
  node borrowed from an STPA does *not* have.
* **Participation** is a membership — many-to-many, the analyses that reason over the node
  without having made it.

The distinction is the whole point of keeping the two relations apart. An FMEA that enumerates
failure modes against an STPA's control structure shows those components in its own working set;
if they render as though the FMEA authored them, the provenance that makes the combined analysis
trustworthy is gone, and so is the reason not to have copied them.

**Confidentiality.** Both facts are resolved against the analyses the reader may already see, and
an analysis absent from that set is silently dropped rather than reported as an id. A node's
membership list, taken as stored, names analyses the reader has no clearance for; publishing them
here would disclose by the back door what a direct read of the analysis answers 404 to. Same
reasoning as `assurance_node_degrees`: a derived value is part of the exposure surface, so it is
derived inside it.
"""

from __future__ import annotations

from typing import Any

#: The fields of an analysis record this surface repeats. A node's detail needs enough to label
#: and link an analysis, not the analysis itself — which has its own endpoint.
_ANALYSIS_SUMMARY_FIELDS = ("analysis_id", "name", "method", "status", "group_id")


def analysis_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    """The label-and-link view of an analysis, for showing beside something it owns or uses."""
    return {field: analysis.get(field) for field in _ANALYSIS_SUMMARY_FIELDS}


def author_of(
    node: dict[str, Any],
    visible_analyses_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """The analysis that produced this node, summarised, or None if the reader cannot see it.

    Takes an already-built index rather than the list, because the callers that need this need it
    per row — a search result set, a picker's candidates — and rebuilding the index per row turns
    one screen into a quadratic scan.
    """
    author = visible_analyses_by_id.get(str(node.get("analysis_id") or ""))
    return analysis_summary(author) if author is not None else None


def analyses_by_id(visible_analyses: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index the visible analyses for repeated `author_of` lookups."""
    return {str(analysis["analysis_id"]): analysis for analysis in visible_analyses}


def provenance(
    node: dict[str, Any],
    *,
    participating_analysis_ids: list[str],
    visible_analyses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return ``authored_by`` and ``participates_in`` for one node.

    ``authored_by`` is None when the node names no analysis, or names one this reader cannot see —
    the two are deliberately indistinguishable, as they are on a direct read.

    ``participates_in`` excludes the authoring analysis even if a membership row happens to name
    it: participation means *another* method drew on this node, and listing the author among the
    borrowers would report the node as borrowed from itself.
    """
    by_id = analyses_by_id(visible_analyses)
    author_id = str(node.get("analysis_id") or "")
    author = by_id.get(author_id)
    participants = [
        analysis_summary(by_id[analysis_id])
        for analysis_id in dict.fromkeys(participating_analysis_ids)
        if analysis_id in by_id and analysis_id != author_id
    ]
    return {
        "authored_by": analysis_summary(author) if author is not None else None,
        "participates_in": participants,
    }
