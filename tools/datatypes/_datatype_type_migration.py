"""Planning and staged application for datatype type-reference migration."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

import yaml  # type: ignore[import-untyped]

from src.application.identifier_allocator import IdentifierAllocator, get_default_allocator
from src.domain.ontology_representation.artifact_types import RepoMount, infer_engagement_label
from src.domain.repository.repo_scope import MountScope, infer_repo_scope
from src.domain.yaml_documents import parse_yaml

_FM_RE = re.compile(r"^---\n(.*?\n)---\n", re.DOTALL)
_ID_RE = re.compile(r"^CLF@[0-9]+\.[A-Za-z0-9_-]+\..+$")
_PRIMITIVES = frozenset({"String", "Integer", "Number", "Boolean", "Date", "DateTime", "UUID"})


class Classifier(NamedTuple):
    old_id: str
    new_id: str
    label: str
    scope: str
    repo_root: Path
    path: Path
    diagram_id: str


class Change(NamedTuple):
    repo_root: Path
    path: Path
    frontmatter: dict[str, object]
    body: str


class MigrationPlan(NamedTuple):
    report: dict[str, object]
    changes: tuple[Change, ...]
    repo_roots: tuple[Path, ...]

    @property
    def unresolved_count(self) -> int:
        return int(self.report["summary"]["unresolved"])  # type: ignore[index]


class MigrationBlockedError(ValueError):
    pass

def _parse(path: Path) -> tuple[dict[str, object], str]:
    text = path.read_text(encoding="utf-8")
    match = _FM_RE.match(text)
    if match is None:
        return {}, text
    loaded: object = parse_yaml(match.group(1)) or {}
    return loaded if isinstance(loaded, dict) else {}, text[match.end():]


def _render(frontmatter: Mapping[str, object], body: str) -> str:
    dumped = str(yaml.safe_dump(dict(frontmatter), sort_keys=False)).strip()
    return f"---\n{dumped}\n---\n{body}"


def _datatype_files(repo_root: Path) -> list[Path]:
    diagram_root = repo_root / "diagram-catalog" / "diagrams"
    if not diagram_root.exists():
        return []
    result: list[Path] = []
    for path in sorted(diagram_root.rglob("*.puml")):
        frontmatter, _ = _parse(path)
        if frontmatter.get("diagram-type") == "datatype":
            result.append(path)
    return result


def _scope(root: Path) -> MountScope:
    return infer_repo_scope(root)


def _replace_ids(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, list):
        return [_replace_ids(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace_ids(item, replacements) for key, item in value.items()}
    return value


def _mapping_key(diagram_id: str, classifier_id: str, attr_name: str) -> str:
    return f"{diagram_id}:{classifier_id}:{attr_name}"


def _classifier_selector(classifier: Classifier) -> str:
    return f"{classifier.diagram_id}:{classifier.old_id}"


def _collect_classifiers(
    parsed: Sequence[tuple[Path, Path, dict[str, object], str]],
    allocator: IdentifierAllocator,
) -> tuple[list[Classifier], dict[Path, dict[str, str]]]:
    classifiers: list[Classifier] = []
    replacements: dict[Path, dict[str, str]] = {}
    for root, path, frontmatter, _body in parsed:
        entities = frontmatter.get("diagram-entities")
        raw_items = entities.get("classifier") if isinstance(entities, dict) else None
        for index, item in enumerate(raw_items if isinstance(raw_items, list) else []):
            if not isinstance(item, dict):
                continue
            old_id = str(item.get("id") or f"__classifier_{index}")
            label = str(item.get("label") or old_id)
            new_id = old_id if _ID_RE.fullmatch(old_id) else allocator.allocate(prefix="CLF", name_hint=label)
            replacements.setdefault(path, {})[old_id] = new_id
            classifiers.append(Classifier(
                old_id,
                new_id,
                label,
                _scope(root),
                root,
                path,
                str(frontmatter.get("artifact-id") or path.stem),
            ))
    return classifiers, replacements


def _visible(candidate: Classifier, referencing_root: Path, referencing_scope: str) -> bool:
    if referencing_scope == "enterprise":
        return candidate.scope == "enterprise"
    return candidate.scope == "enterprise" or candidate.repo_root == referencing_root


def _resolve_legacy_type(
    legacy: str,
    *,
    referencing_root: Path,
    classifiers: Sequence[Classifier],
) -> tuple[dict[str, str] | None, str | None, list[str]]:
    normalized = legacy.strip().casefold()
    all_matches = [item for item in classifiers if item.label.strip().casefold() == normalized]
    visible = [item for item in all_matches if _visible(item, referencing_root, _scope(referencing_root))]
    primitive = next((name for name in _PRIMITIVES if name.casefold() == normalized), None)
    candidate_ids = [_classifier_selector(item) for item in visible]
    if primitive is not None and visible:
        return None, "primitive-shadow", candidate_ids
    if primitive is not None:
        return {"kind": "primitive", "name": primitive}, None, []
    if len(visible) == 1:
        return {"kind": "classifier", "id": visible[0].new_id}, None, candidate_ids
    if len(visible) > 1:
        return None, "multi-match", candidate_ids
    if all_matches:
        return None, "out-of-scope", [_classifier_selector(item) for item in all_matches]
    return None, "multi-match", []


def _valid_mapping(
    mapped: object,
    *,
    referencing_root: Path,
    classifiers: Sequence[Classifier],
) -> dict[str, str] | None:
    if not isinstance(mapped, dict):
        return None
    if mapped.get("kind") == "primitive":
        name = str(mapped.get("name") or "")
        return {"kind": "primitive", "name": name} if name in _PRIMITIVES else None
    if mapped.get("kind") != "classifier":
        return None
    classifier_id = str(mapped.get("id") or "")
    selector = str(mapped.get("selector") or "")
    match = next(
        (
            item for item in classifiers
            if item.new_id == classifier_id or _classifier_selector(item) == selector
        ),
        None,
    )
    if match is None or not _visible(match, referencing_root, _scope(referencing_root)):
        return None
    return {"kind": "classifier", "id": match.new_id}


def plan_migration(
    repo_roots: Sequence[Path],
    *,
    allocator: IdentifierAllocator | None = None,
    mappings: Mapping[str, object] | None = None,
) -> MigrationPlan:
    roots = tuple(root.resolve() for root in repo_roots)
    parsed = [
        (root, path, *_parse(path))
        for root in roots
        for path in _datatype_files(root)
    ]
    classifiers, replacements = _collect_classifiers(parsed, allocator or get_default_allocator())
    decisions: list[dict[str, object]] = []
    changes: list[Change] = []
    mapping_values = mappings or {}

    for root, path, original, body in parsed:
        frontmatter = copy.deepcopy(original)
        diagram_id = str(frontmatter.get("artifact-id") or path.stem)
        path_replacements = replacements.get(path, {})
        raw_entities = copy.deepcopy(frontmatter.get("diagram-entities"))
        items = raw_entities.get("classifier") if isinstance(raw_entities, dict) else None
        for index, item in enumerate(items if isinstance(items, list) else []):
            if isinstance(item, dict):
                old_id = str(item.get("id") or f"__classifier_{index}")
                item["id"] = path_replacements[old_id]
        entities = _replace_ids(raw_entities, path_replacements)
        frontmatter["diagram-entities"] = entities
        for key in ("connections", "bindings"):
            if key in frontmatter:
                frontmatter[key] = _replace_ids(frontmatter[key], path_replacements)

        raw_classifiers = entities.get("classifier") if isinstance(entities, dict) else None
        for classifier in raw_classifiers if isinstance(raw_classifiers, list) else []:
            if not isinstance(classifier, dict):
                continue
            classifier_id = str(classifier.get("id") or "")
            original_classifier_id = next(
                (old for old, new in path_replacements.items() if new == classifier_id),
                classifier_id,
            )
            attributes = classifier.get("attributes")
            for attr in attributes if isinstance(attributes, list) else []:
                if not isinstance(attr, dict) or not isinstance(attr.get("type"), str):
                    continue
                legacy = str(attr["type"])
                attr_name = str(attr.get("name") or "")
                key = _mapping_key(diagram_id, original_classifier_id, attr_name)
                resolved = _valid_mapping(
                    mapping_values.get(key), referencing_root=root, classifiers=classifiers,
                )
                reason: str | None = None
                candidates: list[str] = []
                if resolved is None:
                    resolved, reason, candidates = _resolve_legacy_type(
                        legacy, referencing_root=root, classifiers=classifiers,
                    )
                if resolved is not None:
                    attr["type"] = resolved
                decisions.append({
                    "diagram_id": diagram_id,
                    "classifier_id": classifier_id,
                    "attribute": attr_name,
                    "legacy_type": legacy,
                    "status": "convertible" if resolved is not None else "ambiguous",
                    "proposed_type": resolved,
                    "reason": reason,
                    "candidates": candidates,
                    "mapping_key": key,
                })
        frontmatter["diagram-format-version"] = 2
        changes.append(Change(root, path, frontmatter, body))

    unresolved = sum(item["status"] == "ambiguous" for item in decisions)
    report: dict[str, object] = {
        "format_version": 1,
        "repositories": [str(root) for root in roots],
        "classifiers": [
            {
                "path": str(item.path),
                "old_id": item.old_id,
                "new_id": item.new_id,
                "label": item.label,
                "selector": _classifier_selector(item),
            }
            for item in classifiers
        ],
        "attributes": decisions,
        "summary": {
            "diagrams": len(changes),
            "classifiers": len(classifiers),
            "attributes": len(decisions),
            "convertible": len(decisions) - unresolved,
            "unresolved": unresolved,
        },
    }
    return MigrationPlan(report, tuple(changes), roots)


def _verify_staged_roots(staged_by_live: Mapping[Path, Path]) -> list[str]:
    from src.application.candidate_repository import committed_repository
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
    from src.infrastructure.artifact_index.service import ArtifactIndex

    errors: list[str] = []
    enterprise = [
        RepoMount(staged, "enterprise", "enterprise")
        for live, staged in staged_by_live.items() if _scope(live) == "enterprise"
    ]
    contexts: list[tuple[Path, list[RepoMount]]] = []
    for live, staged in staged_by_live.items():
        scope = _scope(live)
        mount = RepoMount(staged, scope, infer_engagement_label(live, scope=scope))
        contexts.append((staged, [mount] if scope == "enterprise" else [mount, *enterprise]))
    catalogs = build_runtime_catalogs(get_module_registry())
    for root, mounts in contexts:
        store = ArtifactIndex(mounts)
        verifier = ArtifactVerifier(
            ArtifactRegistry(store),
            catalogs=catalogs,
            committed_repo=committed_repository(store),
        )
        errors.extend(
            f"{issue.code}: {issue.message} ({issue.location})"
            for result in verifier.verify_all(root, include_diagrams=True)
            for issue in result.issues
            if issue.severity == "error"
        )
    return errors


def apply_migration(
    plan: MigrationPlan,
    *,
    verify: Callable[[Mapping[Path, Path]], list[str]] = _verify_staged_roots,
) -> tuple[Path, ...]:
    if plan.unresolved_count:
        raise MigrationBlockedError(
            f"Migration has {plan.unresolved_count} unresolved attribute type reference(s)"
        )
    from src.infrastructure.write.artifact_write.batch_transaction import (
        commit_staged_repo,
        create_staging_repo,
    )

    roots = sorted(plan.repo_roots)
    staging = {root: create_staging_repo(root) for root in roots}
    try:
        staged_by_live = {root: staged for root, (_handle, staged) in staging.items()}
        touched_by_live: dict[Path, set[Path]] = {root: set() for root in roots}
        for change in plan.changes:
            relative = change.path.relative_to(change.repo_root)
            staged_path = staged_by_live[change.repo_root] / relative
            staged_path.write_text(_render(change.frontmatter, change.body), encoding="utf-8")
            touched_by_live[change.repo_root].add(staged_path)
        errors = verify(staged_by_live)
        if errors:
            raise MigrationBlockedError("Staged verification failed:\n" + "\n".join(errors))
        changed: list[Path] = []
        for root in roots:
            changed.extend(
                commit_staged_repo(
                    live_root=root,
                    staged_root=staged_by_live[root],
                    touched_paths=touched_by_live[root],
                    rebuild_index=lambda _result: None,
                ).changed_paths
            )
        return tuple(changed)
    finally:
        for handle, _staged in staging.values():
            handle.cleanup()
