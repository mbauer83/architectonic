"""How a diagram file is written, and read back when a rewrite must not lose it.

Split from `artifact_write_formatting`, which had grown to hold four unrelated artifact formatters
under one name. The two halves here belong together: one writes a diagram's frontmatter, the other
reads it back so a caller changing one part hands the rest over untouched.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TypedDict

import yaml  # type: ignore[import-untyped]


def _dump_yaml_text(data: object) -> str:
    """Frontmatter YAML, dumped exactly as the other artifact formatters dump it.

    Serialisation is deliberately not centralised in this project — `yaml_documents` owns parsing and
    says so — and the options here are load-bearing: `sort_keys=False` keeps the declared key order a
    reader relies on, and the strip keeps the delimiter on its own line.
    """
    dumped = yaml.safe_dump(data, sort_keys=False)
    if not isinstance(dumped, str):
        raise TypeError("yaml.safe_dump returned non-string output")
    return dumped.strip()


class CarriedDiagramFields(TypedDict, total=False):
    """The `format_diagram_puml` arguments a rewrite must hand back unchanged."""

    keywords: list[str]
    diagram_format_version: int
    manual_layout: bool
    tlp: str
    viewpoint: dict[str, object]
    view_derivations: list[dict[str, object]]
    bindings: list[dict[str, object]]
    edge_labels: dict[str, str]
    authored_groupings: list[dict[str, object]]


def carried_diagram_fields(frontmatter: Mapping[str, object]) -> CarriedDiagramFields:
    """The fields a caller rewriting part of a diagram must pass back, read from its frontmatter.

    **`format_diagram_puml` writes only what it is given, so a field omitted is a field deleted.**
    Enumerating them at each call site is what went wrong: the project cascade delete passed eleven
    arguments and silently dropped nine, so deleting a model project stripped every foreign diagram's
    `keywords`, `authored-groupings`, `bindings`, `edge-labels`, `viewpoint`, `view_derivations`,
    `diagram-format-version`, `manual-layout` — which is what stops a hand-laid body being
    regenerated — and `tlp`, a confidentiality classification. Measured on a fixture repository:
    two keywords and one authored grouping present before the delete, both absent after, with the
    operation reporting `applied: true` and no warning.

    Named here because this module owns the mapping between a diagram's frontmatter keys and these
    arguments; a second reading of that mapping is how the nine went missing in the first place.
    """
    carried: CarriedDiagramFields = {}
    if isinstance(keywords := frontmatter.get("keywords"), list):
        carried["keywords"] = [str(k) for k in keywords]
    if isinstance(version := frontmatter.get("diagram-format-version"), int):
        carried["diagram_format_version"] = version
    if frontmatter.get("manual-layout") is True:
        carried["manual_layout"] = True
    if isinstance(tlp := frontmatter.get("tlp"), str) and tlp:
        carried["tlp"] = tlp
    if isinstance(viewpoint := frontmatter.get("viewpoint"), dict):
        carried["viewpoint"] = dict(viewpoint)
    if isinstance(derivations := frontmatter.get("view_derivations"), list):
        carried["view_derivations"] = [dict(d) for d in derivations if isinstance(d, dict)]
    if isinstance(bindings := frontmatter.get("bindings"), list):
        carried["bindings"] = [dict(b) for b in bindings if isinstance(b, dict)]
    if isinstance(labels := frontmatter.get("edge-labels"), dict):
        carried["edge_labels"] = {str(k): str(v) for k, v in labels.items()}
    if isinstance(groupings := frontmatter.get("authored-groupings"), list):
        carried["authored_groupings"] = [dict(g) for g in groupings if isinstance(g, dict)]
    return carried


def format_diagram_puml(
    *,
    artifact_id: str,
    diagram_type: str,
    name: str,
    version: str,
    status: str,
    last_updated: str,
    keywords: list[str] | None = None,
    entity_ids_used: list[str] | None = None,
    connection_ids_used: list[str] | None = None,
    puml_body: str,
    diagram_entities: dict[str, object] | None = None,
    diagram_connections: list[dict[str, object]] | None = None,
    view_derivations: list[dict[str, object]] | None = None,
    bindings: list[dict[str, object]] | None = None,
    edge_labels: dict[str, str] | None = None,
    tlp: str | None = None,
    diagram_format_version: int | None = None,
    viewpoint: dict[str, object] | None = None,
    authored_groupings: list[dict[str, object]] | None = None,
    manual_layout: bool = False,
) -> str:
    # A diagram name is a single-line label. Collapse control characters in the
    # (user-controlled) name so it cannot break out of the frontmatter `name:` value
    # or the `title` line into a standalone preprocessor directive that the renderer
    # would execute (e.g. "x\n!include /etc/passwd" reading a server file into the SVG).
    name = re.sub(r"[\r\n\t]+", " ", name).strip()
    frontmatter: dict[str, object] = {
        "artifact-id": artifact_id,
        "artifact-type": "diagram",
        "name": name,
        "version": version,
        "status": status,
    }
    if keywords:
        frontmatter["keywords"] = keywords
    frontmatter["diagram-type"] = diagram_type
    if diagram_format_version is not None:
        frontmatter["diagram-format-version"] = diagram_format_version
    if manual_layout:
        frontmatter["manual-layout"] = True  # hand-tuned body: sync reconciles bindings only
    if tlp:
        frontmatter["tlp"] = tlp
    if viewpoint is not None:
        frontmatter["viewpoint"] = viewpoint
    if entity_ids_used:
        frontmatter["entity-ids-used"] = entity_ids_used
    if connection_ids_used:
        frontmatter["connection-ids-used"] = connection_ids_used
    if diagram_entities is not None:
        frontmatter["diagram-entities"] = diagram_entities
    if diagram_connections is not None:
        frontmatter["connections"] = diagram_connections
    if view_derivations:
        frontmatter["view_derivations"] = view_derivations
    if bindings:
        frontmatter["bindings"] = bindings
    if edge_labels:
        frontmatter["edge-labels"] = edge_labels
    if authored_groupings:
        frontmatter["authored-groupings"] = authored_groupings
    frontmatter["last-updated"] = last_updated

    ordered_keys = [
        "artifact-id", "artifact-type", "name", "version", "status", "keywords",
        "diagram-type", "diagram-format-version", "manual-layout", "tlp", "viewpoint",
        "entity-ids-used", "connection-ids-used", "diagram-entities", "connections",
        "view_derivations", "bindings", "edge-labels", "authored-groupings", "last-updated",
    ]
    fm_out = {key: frontmatter[key] for key in ordered_keys if key in frontmatter}
    yaml_text = _dump_yaml_text(fm_out)

    body = _ensure_visible_title(puml_body, name)
    return f"---\n{yaml_text}\n---\n{body}"


def _ensure_visible_title(puml_body: str, title_text: str) -> str:
    lines = puml_body.strip("\n").splitlines()
    if not lines:
        return puml_body.strip("\n") + "\n"

    has_title = any(
        (not line.lstrip().startswith("'")) and re.match(r"^\s*title(\s|$)", line, flags=re.IGNORECASE)
        for line in lines
    )
    if has_title:
        return puml_body.strip("\n") + "\n"

    start_idx = next((i for i, line in enumerate(lines) if line.strip().startswith("@startuml")), 0)
    insert_idx = start_idx + 1
    for i in range(start_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("'"):
            continue
        if stripped.lower().startswith("!include"):
            insert_idx = i + 1
            continue
        break

    lines.insert(insert_idx, f"title {title_text}")
    return "\n".join(lines) + "\n"
