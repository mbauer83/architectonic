"""Scratchpads on disk: one YAML document per scratchpad, git-diffable on purpose.

**Not** frontmatter-plus-body. Frontmatter exists to separate metadata from prose, and a scratchpad
has no prose body — its prose lives in fields. Pretending otherwise would add ceremony every reader
and every parser then has to strip. The precedent is the diagram, which already proves the
repository tolerates a body that is not markdown so long as identity and metadata are conventional.

Two properties make a scratchpad reviewable rather than merely stored, and both are this module's
responsibility because both are about serialisation rather than about the aggregate:

* **stable order** — every collection is written sorted by id, so re-saving an unchanged scratchpad
  produces an unchanged file, and a diff shows what moved rather than how the dict happened to
  iterate;
* **layout last, and snapped** — geometry is one block at the end, on the grid the domain defines,
  so an afternoon of tidying and an afternoon of thinking land in different parts of the file.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from src.application.scratchpad.ports import (
    ScratchpadNotFoundError,
    ScratchpadSummary,
    ScratchpadVersionConflictError,
)
from src.domain.artifact_id import stable_id
from src.domain.repository.repo_layout import SCRATCHPADS
from src.domain.scratchpad import (
    Area,
    Group,
    Layout,
    Link,
    ModelRef,
    Note,
    Point,
    Rect,
    Scratchpad,
    scratchpad_from_parts,
)

#: The file suffix. Two dots so the kind is readable in a directory listing and a glob for
#: scratchpads cannot also match a stray `.yaml` someone dropped beside them.
SUFFIX = ".scratchpad.yaml"

_UNCATEGORIZED = "uncategorized"


def _bump(version: str) -> str:
    """Next patch version. The version is a concurrency token first and a version second, so it
    only has to move on every write — but it moves the way the rest of the repository's do."""
    parts = version.split(".")
    if len(parts) == 3 and parts[2].isdigit():
        return f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
    return "0.1.1"


class YamlScratchpadRepository:
    """`ScratchpadRepositoryPort` over `scratchpads/<group>/<id>.scratchpad.yaml`."""

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root / SCRATCHPADS

    # ── Reading ──────────────────────────────────────────────────────────────

    def _paths(self) -> list[Path]:
        return sorted(self._root.rglob(f"*{SUFFIX}")) if self._root.is_dir() else []

    def _path_for(self, artifact_id: str) -> Path | None:
        short = stable_id(artifact_id)
        for path in self._paths():
            name = path.name[: -len(SUFFIX)]
            if name == artifact_id or stable_id(name) == short:
                return path
        return None

    def list_scratchpads(self, *, group: str | None = None, status: str | None = None) -> list[ScratchpadSummary]:
        summaries: list[ScratchpadSummary] = []
        for path in self._paths():
            raw = _read_yaml(path)
            if not raw:
                continue
            found_group = path.parent.name if path.parent != self._root else _UNCATEGORIZED
            found_status = str(raw.get("status") or "draft")
            if group is not None and found_group != group:
                continue
            if status is not None and found_status != status:
                continue
            summaries.append(ScratchpadSummary(
                artifact_id=str(raw.get("artifact-id") or path.name[: -len(SUFFIX)]),
                name=str(raw.get("name") or ""),
                description=str(raw.get("description") or ""),
                status=found_status,
                version=str(raw.get("version") or "0.1.0"),
                group=found_group,
                meta_ontology=str(raw.get("meta-ontology") or "archimate-4"),
                note_count=len(raw.get("notes") or []),
            ))
        return sorted(summaries, key=lambda summary: summary.artifact_id)

    def load(self, artifact_id: str) -> Scratchpad:
        path = self._path_for(artifact_id)
        if path is None:
            raise ScratchpadNotFoundError(f"no scratchpad {artifact_id!r} under {self._root}")
        return deserialize(_read_yaml(path))

    def group_of(self, artifact_id: str) -> str:
        path = self._path_for(artifact_id)
        if path is None:
            raise ScratchpadNotFoundError(f"no scratchpad {artifact_id!r} under {self._root}")
        return path.parent.name if path.parent != self._root else _UNCATEGORIZED

    # ── Writing ──────────────────────────────────────────────────────────────

    def save(self, scratchpad: Scratchpad, *, group: str, expected_version: str | None = None) -> Scratchpad:
        existing = self._path_for(scratchpad.artifact_id)
        if existing is not None:
            stored_version = str(_read_yaml(existing).get("version") or "0.1.0")
            if expected_version is None or expected_version != stored_version:
                raise ScratchpadVersionConflictError(
                    scratchpad.artifact_id, expected_version or "(none)", stored_version
                )
        stored = replace(scratchpad, version=_bump(scratchpad.version), layout=scratchpad.layout.snapped())
        stored.validate()
        target = self._root / group / f"{stored.artifact_id}{SUFFIX}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialize(stored), encoding="utf-8")
        # A re-home is a move, not a copy: leaving the old file behind would make one scratchpad
        # answer to two ids the moment either is edited.
        if existing is not None and existing != target:
            existing.unlink(missing_ok=True)
        return stored

    def delete(self, artifact_id: str) -> None:
        path = self._path_for(artifact_id)
        if path is None:
            raise ScratchpadNotFoundError(f"no scratchpad {artifact_id!r} under {self._root}")
        path.unlink()


# ── Serialisation ────────────────────────────────────────────────────────────


def _read_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _drop_empty(mapping: dict[str, Any]) -> dict[str, Any]:
    """Omit what carries no information. A file full of `null`s reads as a file full of decisions."""
    return {key: value for key, value in mapping.items() if value not in (None, "", (), [], {})}


def _note_dict(note: Note) -> dict[str, Any]:
    return _drop_empty({
        "id": note.id,
        "title": note.title,
        "body": note.body,
        "destination": note.destination if note.destination != "undecided" else "",
        "element-type": note.element_type,
        "specialization": note.specialization,
        "document-type": note.document_type,
        "model-ref": _drop_empty({"artifact-id": note.model_ref.artifact_id, "kind": note.model_ref.kind})
                     if note.model_ref else None,
        "attributes": dict(note.attributes),
    })


def _link_dict(link: Link) -> dict[str, Any]:
    return _drop_empty({
        "id": link.id,
        "source": link.source,
        "target": link.target,
        "connection-type": link.connection_type,
        "model-ref": _drop_empty({"artifact-id": link.model_ref.artifact_id, "kind": link.model_ref.kind})
                     if link.model_ref else None,
    })


def serialize(scratchpad: Scratchpad) -> str:
    document = _drop_empty({
        "artifact-id": scratchpad.artifact_id,
        "artifact-type": "scratchpad",
        "name": scratchpad.name,
        "description": scratchpad.description,
        "version": scratchpad.version,
        "status": scratchpad.status,
        "meta-ontology": scratchpad.meta_ontology,
        "attributes": dict(scratchpad.attributes),
        "areas": [
            _drop_empty({
                "id": area.id,
                "label": area.label,
                "permits": _drop_empty({
                    "elements": list(area.permitted_element_types),
                    "documents": list(area.permitted_document_types),
                }),
            })
            for area in sorted(scratchpad.areas, key=lambda item: item.id)
        ],
        "notes": [_note_dict(note) for note in sorted(scratchpad.notes, key=lambda item: item.id)],
        "groups": [
            _drop_empty({"id": group.id, "label": group.label, "members": sorted(group.members)})
            for group in sorted(scratchpad.groups, key=lambda item: item.id)
        ],
        "links": [_link_dict(link) for link in sorted(scratchpad.links, key=lambda item: item.id)],
    })
    # Layout last and separate: a content change and a movement then land in different parts of the
    # file, which is the whole reason the aggregate keeps them apart.
    layout = _drop_empty({
        "areas": {key: [rect.x, rect.y, rect.width, rect.height]
                  for key, rect in sorted(scratchpad.layout.areas.items())},
        "notes": {key: [point.x, point.y] for key, point in sorted(scratchpad.layout.notes.items())},
        "groups": {key: [rect.x, rect.y, rect.width, rect.height]
                   for key, rect in sorted(scratchpad.layout.groups.items())},
    })
    if layout:
        document["layout"] = layout
    return str(yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100))


def _model_ref(raw: object) -> ModelRef | None:
    if not isinstance(raw, dict) or not raw.get("artifact-id"):
        return None
    kind = str(raw.get("kind") or "bound")
    return ModelRef(artifact_id=str(raw["artifact-id"]), kind="realized" if kind == "realized" else "bound")


def deserialize(raw: dict[str, Any]) -> Scratchpad:
    def rows(key: str) -> list[dict[str, Any]]:
        value = raw.get(key)
        return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []

    raw_layout = raw.get("layout")
    layout_raw: dict[str, Any] = raw_layout if isinstance(raw_layout, dict) else {}

    def rects(key: str) -> dict[str, Rect]:
        block = layout_raw.get(key)
        return {str(k): Rect(*(float(n) for n in v)) for k, v in block.items()} if isinstance(block, dict) else {}

    points_block = layout_raw.get("notes")
    points = (
        {str(k): Point(float(v[0]), float(v[1])) for k, v in points_block.items()}
        if isinstance(points_block, dict) else {}
    )

    return scratchpad_from_parts(
        artifact_id=str(raw.get("artifact-id") or ""),
        name=str(raw.get("name") or ""),
        description=str(raw.get("description") or ""),
        version=str(raw.get("version") or "0.1.0"),
        status=str(raw.get("status") or "draft"),
        meta_ontology=str(raw.get("meta-ontology") or "archimate-4"),
        attributes=dict(raw.get("attributes") or {}),
        areas=[
            Area(
                id=str(row.get("id") or ""),
                label=str(row.get("label") or ""),
                permitted_element_types=tuple(str(v) for v in (row.get("permits") or {}).get("elements") or ()),
                permitted_document_types=tuple(str(v) for v in (row.get("permits") or {}).get("documents") or ()),
            )
            for row in rows("areas")
        ],
        notes=[
            Note(
                id=str(row.get("id") or ""),
                title=str(row.get("title") or ""),
                body=str(row.get("body") or ""),
                destination=str(row.get("destination") or "undecided"),  # type: ignore[arg-type]
                element_type=row.get("element-type"),
                specialization=row.get("specialization"),
                document_type=row.get("document-type"),
                model_ref=_model_ref(row.get("model-ref")),
                attributes=dict(row.get("attributes") or {}),
            )
            for row in rows("notes")
        ],
        links=[
            Link(
                id=str(row.get("id") or ""),
                source=str(row.get("source") or ""),
                target=str(row.get("target") or ""),
                connection_type=row.get("connection-type"),
                model_ref=_model_ref(row.get("model-ref")),
            )
            for row in rows("links")
        ],
        groups=[
            Group(
                id=str(row.get("id") or ""),
                label=str(row.get("label") or ""),
                members=tuple(str(v) for v in row.get("members") or ()),
            )
            for row in rows("groups")
        ],
        layout=Layout(areas=rects("areas"), notes=points, groups=rects("groups")),
    )
