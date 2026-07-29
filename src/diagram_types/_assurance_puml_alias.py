"""The PlantUML alias an assurance node is drawn under — one definition, shared by the types that draw them.

Lives beside the assurance diagram types rather than in the domain, because an alias is a
*presentation* concern: it exists only inside a PlantUML body and the SVG rendered from it. Nothing in
the model knows or cares what a shape is called. It is shared because several diagram types in the
assurance module render the same nodes and must name them identically.

The rendered SVG is the only place a browser can learn which shape is which node: PlantUML emits the
alias as `data-qualified-name`, and the assurance viewer maps that back to a node id to make shapes
selectable. So the alias is a contract between the renderer and the client, not an internal detail of
one diagram type.

It was written twice, once per diagram type, and the two drifted: control-structure emitted a `N_`
prefix and bowtie did not, while the client reconstructed the prefixed form for both. The result was
silent and total — every shape in a bowtie was inert, with no error anywhere, because a click handler
is only attached to a group whose alias was recognised.

The prefix stays because the client already expects it, and because an alias that cannot begin with a
digit is worth guaranteeing rather than relying on every id prefix happening to start with a letter.
"""

from __future__ import annotations

import re

_NON_ALIAS_CHARS = re.compile(r"[^A-Za-z0-9_]")
_REPEATED_UNDERSCORE = re.compile(r"_{2,}")

#: Prefix the assurance viewer reconstructs when mapping a rendered shape back to its node.
#: Changing it means changing `assuranceNodeAlias` in the frontend in the same commit.
ALIAS_PREFIX = "N_"


def safe_alias(node_id: str) -> str:
    """A PlantUML-safe alias for an assurance node id, stable across every content source."""
    collapsed = _REPEATED_UNDERSCORE.sub("_", _NON_ALIAS_CHARS.sub("_", node_id)).strip("_")
    return f"{ALIAS_PREFIX}{collapsed or 'node'}"
