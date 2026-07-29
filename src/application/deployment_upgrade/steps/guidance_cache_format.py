"""Operational migration: bring an already-imported guidance cache to the current format.

Guidance is imported latest-format-only; an older imported cache is migrated OFFLINE here
(``arch-repair upgrade``, system down) rather than re-imported blindly — the licensed source may
no longer be reachable from the machine that runs the upgrade.

The current format nests each meta-ontology's guidance the way its declared hierarchy nests, so the
migration is structural, not a header patch: the workspace map of topics collapses into the level's
one text, the meta-ontology node's context moves onto the alias itself, and each entity type moves
under the domain node its module declares for it. That last move needs the module's guidance tree,
which is injected — without it the cache is reported as needing a re-import instead of being
rewritten half-correctly. A document whose format is unreadable or NEWER than supported blocks the
commit rather than being rewritten.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

import yaml  # type: ignore[import-untyped]

from src.application.deployment_upgrade.ports import (
    OperationalTargetUnitOfWork,
    OperationalTargetView,
)
from src.domain.guidance.guidance import (
    CONNECTION_TYPES_KEY,
    CONTEXT_KEY,
    ENTITY_TYPES_KEY,
    GUIDANCE_FORMAT,
)
from src.domain.guidance.guidance_hierarchy import GuidanceHierarchy
from src.domain.guidance.guidance_hierarchy_source import ENTITY_TYPE_LEVEL, META_ONTOLOGY_LEVEL
from src.domain.repository.operational_upgrade import TargetKind
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding

_FORMAT_RE = re.compile(r"^guidance_format:[ \t]*(\d+)[ \t]*$", re.MULTILINE)
_OUTDATED_PREFIX = "guidance-format-outdated:"
_WORKSPACE_KEY = "workspace"
_META_ONTOLOGIES_KEY = "meta_ontologies"


class GuidanceCacheFormatStep:
    """Restructures each cached guidance document into the current format; binds to the deployment
    guidance-cache target discovered by arch-repair (``~/.config/arch-repo/guidance-cache/`` by
    default).

    ``hierarchies`` maps a meta-ontology alias to its declared guidance tree — what tells the
    migration which domain node each entity type belongs under. An alias missing from it cannot be
    restructured here, so its cache is reported for manual re-import.
    """

    id = "guidance-0003-hierarchy-shaped-document"
    version = GUIDANCE_FORMAT
    kind: TargetKind = "guidance_cache"
    description = "Guidance cache → current format (nest each type under the domain its module declares)"

    def __init__(self, hierarchies: Mapping[str, GuidanceHierarchy] | None = None) -> None:
        self._hierarchies: Mapping[str, GuidanceHierarchy] = hierarchies or {}

    def detect(self, view: OperationalTargetView) -> list[UpgradeFinding]:
        findings: list[UpgradeFinding] = []
        for name in view.list_files("*.guidance.yaml"):
            content = view.read_text(name)
            if content is None:
                continue
            findings.extend(self._findings_for(name, content))
        return findings

    def _findings_for(self, name: str, content: str) -> list[UpgradeFinding]:
        match = _FORMAT_RE.search(content)
        if match is None:
            return [self._blocking(name, f"{name}: no readable guidance_format header")]
        current = int(match.group(1))
        if current == GUIDANCE_FORMAT:
            return []
        if current > GUIDANCE_FORMAT:
            return [self._blocking(
                name,
                f"{name}: guidance_format {current} is newer than the supported "
                f"{GUIDANCE_FORMAT}; wrote by a newer release",
                instructions="Upgrade the software to a release that supports this format.",
            )]
        migrated = self._migrate(content)
        if migrated is None:
            return [self._blocking(
                name,
                f"{name}: guidance_format {current} cannot be restructured here — the guidance tree "
                "of at least one meta-ontology in it is unknown to this software",
            )]
        return [UpgradeFinding(
            step_id=self.id,
            finding_id=f"{_OUTDATED_PREFIX}{name}",
            location=name,
            description=f"{name}: guidance_format {current}; the current format is {GUIDANCE_FORMAT}",
            severity="warning",
            auto_migratable=True,
            rewrite_summary=(
                "restructure into the current format: one workspace text, each entity type under "
                "the domain node its module declares, each meta-ontology context on its alias"
            ),
        )]

    def _blocking(self, name: str, description: str, *, instructions: str | None = None) -> UpgradeFinding:
        return UpgradeFinding(
            step_id=self.id,
            finding_id=f"guidance-format-unmigratable:{name}",
            location=name,
            description=description,
            severity="error",
            auto_migratable=False,
            manual_instructions=instructions or "Re-import this guidance source with arch-import-guidance.",
            blocks_commit=True,
        )

    def apply(
        self,
        view: OperationalTargetView,
        uow: OperationalTargetUnitOfWork,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        applied: list[AppliedFinding] = []
        for finding in findings:
            if not finding.finding_id.startswith(_OUTDATED_PREFIX):
                continue
            content = view.read_text(finding.location)
            migrated = self._migrate(content) if content is not None else None
            if migrated is None:
                continue
            uow.write_text(finding.location, migrated)
            applied.append(AppliedFinding(
                finding=finding,
                outcome="applied",
                detail=f"restructured into guidance_format {GUIDANCE_FORMAT}",
            ))
        return applied

    def _migrate(self, content: str) -> str | None:
        """The document restructured into the current format, or None when it cannot be — a
        migration that would drop or misfile guidance must not run at all."""
        try:
            document = yaml.safe_load(content)
        except yaml.YAMLError:
            return None
        if not isinstance(document, dict):
            return None
        migrated: dict[str, object] = {"guidance_format": GUIDANCE_FORMAT}
        if _WORKSPACE_KEY in document:
            migrated[_WORKSPACE_KEY] = _migrated_workspace(document[_WORKSPACE_KEY])
        aliases = document.get(_META_ONTOLOGIES_KEY)
        if isinstance(aliases, Mapping):
            trees: dict[str, object] = {}
            for alias, alias_data in aliases.items():
                hierarchy = self._hierarchies.get(str(alias))
                if hierarchy is None or not isinstance(alias_data, Mapping):
                    return None
                trees[str(alias)] = _migrated_alias(alias_data, hierarchy)
            migrated[_META_ONTOLOGIES_KEY] = trees
        # Anything else the document carries is content this migration has no opinion about, so it
        # survives rather than being dropped by the re-serialization.
        migrated.update({key: value for key, value in document.items() if key not in migrated})
        return str(yaml.safe_dump(migrated, sort_keys=False, allow_unicode=True))


def _migrated_workspace(section: object) -> str:
    """One workspace text out of whatever the older format held: already a string, or the topic
    map's texts in source order, joined into paragraphs so nothing authored is lost."""
    if isinstance(section, str):
        return section
    if not isinstance(section, Mapping):
        return ""
    texts = [
        entry[CONTEXT_KEY].strip()
        for entry in section.values()
        if isinstance(entry, Mapping) and isinstance(entry.get(CONTEXT_KEY), str) and entry[CONTEXT_KEY].strip()
    ]
    return "\n\n".join(texts)


def _migrated_alias(alias_data: Mapping[str, object], hierarchy: GuidanceHierarchy) -> dict[str, object]:
    """One alias's flat, level-keyed sections re-nested along its declared hierarchy."""
    tree: dict[str, object] = {}
    meta_context = _level_contexts(alias_data, META_ONTOLOGY_LEVEL)
    if meta_context:
        tree[CONTEXT_KEY] = next(iter(meta_context.values()))
    connection_types = alias_data.get(CONNECTION_TYPES_KEY)
    if isinstance(connection_types, Mapping):
        tree[CONNECTION_TYPES_KEY] = dict(connection_types)

    parent_level = hierarchy.parent_level_of(ENTITY_TYPE_LEVEL)
    node_contexts = _level_contexts(alias_data, parent_level.id) if parent_level is not None else {}
    types_by_node = _types_by_node(alias_data, hierarchy)
    for node_id in (*node_contexts, *(n for n in types_by_node if n not in node_contexts)):
        node: dict[str, object] = {}
        context = node_contexts.get(node_id)
        if context:
            node[CONTEXT_KEY] = context
        types = types_by_node.get(node_id)
        if types:
            node[ENTITY_TYPES_KEY] = types
        tree[node_id] = node
    return tree


def _types_by_node(
    alias_data: Mapping[str, object], hierarchy: GuidanceHierarchy
) -> dict[str, dict[str, object]]:
    """The older document's flat entity-type slots, grouped under the node each type's module
    declares as its parent. A type the hierarchy does not know is dropped — it was already dead
    weight in the cache, since the overlay only ever serves types the module declares."""
    entity_types = alias_data.get(ENTITY_TYPES_KEY)
    if not isinstance(entity_types, Mapping):
        return {}
    grouped: dict[str, dict[str, object]] = {}
    for type_name, type_data in entity_types.items():
        node_id = _declared_parent(hierarchy, str(type_name))
        if node_id is None:
            continue
        grouped.setdefault(node_id, {})[str(type_name)] = type_data
    return grouped


def _level_contexts(alias_data: Mapping[str, object], level_id: str) -> dict[str, str]:
    """The ``<node>: {context: ...}`` texts an older document filed under one level key."""
    section = alias_data.get(level_id)
    if not isinstance(section, Mapping):
        return {}
    return {
        str(node_id): node_data[CONTEXT_KEY]
        for node_id, node_data in section.items()
        if isinstance(node_data, Mapping) and isinstance(node_data.get(CONTEXT_KEY), str)
    }


def _declared_parent(hierarchy: GuidanceHierarchy, type_name: str) -> str | None:
    return next(
        (
            node.parent_node_id
            for node in hierarchy.nodes
            if node.level_id == ENTITY_TYPE_LEVEL and node.node_id == type_name
        ),
        None,
    )
