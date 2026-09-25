"""Verify what a diagram says about its elements' icons.

- **E364** an icon reference is malformed, or names no icon of the library (`ICO@…`) or of the diagram
  itself (`local:…`, its `diagram-entities.icons`);
- **E365** the diagram's type draws no icons, or not in the style asked for;
- **W361** an assignment's icon does not apply to the element or type it is assigned to — the render
  passes it over for the next level, which is why a type changed elsewhere makes this a warning;
- **W362** a `type_icons` key names no type or specialization the product knows.

An instance is classified the two ways that are not a notation's own: a model entity through the
registry, and a node the diagram hosts through the `diagram-entities` list its type keys. An instance
addressed any other way (an occurrence) is not classified here, and no applicability is claimed for it.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.application.icons.effective_icons import (
    DISPLAY_ICONS_KEY,
    LOCAL_ICONS_KEY,
    TYPE_ICONS_KEY,
    icon_assignments,
    malformed_icon_entries,
)
from src.application.icons.icon_vocabulary import icon_applicability_names
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.application.verification.verifier_ports import IconLibrary
from src.domain.icons.applicability import Applicability
from src.domain.icons.icon_ref import IconRef, LocalIcon, SharedIcon
from src.domain.ontology_representation.ontology_protocol import IconPresentingRenderer


def check_icon_assignments(
    fm: Mapping[str, object],
    registry: ArtifactRegistry,
    library: IconLibrary,
    catalogs: RuntimeCatalogs,
    result: VerificationResult,
    loc: str,
) -> None:
    raw = fm.get("diagram-entities")
    diagram_entities = raw if isinstance(raw, Mapping) else {}
    assignments = icon_assignments(diagram_entities)
    malformed = malformed_icon_entries(diagram_entities)
    if not (assignments.by_instance or assignments.by_name or malformed):
        return
    issues = [_error("E364", f"{statement} {key!r}: {reason}", loc) for statement, key, reason in malformed]
    styles = _styles_drawn(str(fm.get("diagram-type", "")), catalogs)
    local_keys = _local_keys(diagram_entities)
    known = icon_applicability_names(catalogs)
    for key, ref in assignments.by_instance.items():
        issues += _reference_issues(DISPLAY_ICONS_KEY, key, ref, styles, local_keys, library, loc)
        names = _instance_names(key, diagram_entities, registry)
        issues += _applicability_issues(DISPLAY_ICONS_KEY, key, ref, names, library, loc)
    for name, ref in assignments.by_name.items():
        issues += _reference_issues(TYPE_ICONS_KEY, name, ref, styles, local_keys, library, loc)
        if name not in known:
            unknown = f"{TYPE_ICONS_KEY} names '{name}', which is no known type or specialization"
            issues.append(_warning("W362", unknown, loc))
        issues += _applicability_issues(TYPE_ICONS_KEY, name, ref, frozenset({name}), library, loc)
    result.issues.extend(issues)


def _styles_drawn(diagram_type: str, catalogs: RuntimeCatalogs) -> tuple[str, ...]:
    module = catalogs.diagram_types.find_diagram_type(diagram_type)
    if module is None or not isinstance(module.renderer, IconPresentingRenderer):
        return ()
    return module.renderer.icon_styles


def _local_keys(diagram_entities: Mapping[str, object]) -> frozenset[str]:
    raw = diagram_entities.get(LOCAL_ICONS_KEY)
    return frozenset(str(key) for key in raw) if isinstance(raw, Mapping) else frozenset()


def _reference_issues(
    statement: str,
    key: str,
    ref: IconRef,
    styles: tuple[str, ...],
    local_keys: frozenset[str],
    library: IconLibrary,
    loc: str,
) -> list[Issue]:
    where = f"{statement} {key!r}"
    if not styles:
        return [_error("E365", f"{where}: this diagram type draws no icons", loc)]
    if ref.style is not None and ref.style not in styles:
        return [_error("E365", f"{where}: this diagram type draws icons as {', '.join(styles)}, not {ref.style}", loc)]
    match ref.target:
        case SharedIcon(icon_id=icon_id) if library.get_icon(icon_id) is None:
            return [_error("E364", f"{where} names {icon_id}, which the library does not hold", loc)]
        case LocalIcon(key=local) if local not in local_keys:
            missing = f"{where} names local:{local}, which this diagram's own icons do not include"
            return [_error("E364", missing, loc)]
        case _:
            return []


def _applicability_issues(
    statement: str, key: str, ref: IconRef, names: frozenset[str] | None, library: IconLibrary, loc: str
) -> list[Issue]:
    applies_to = _applies_to(ref, library)
    if names is None or applies_to is None or applies_to.admits(names):
        return []
    what = ", ".join(sorted(applies_to.names))
    return [_warning("W361", f"{statement} {key!r}: the icon applies to {what}, not to this element", loc)]


def _applies_to(ref: IconRef, library: IconLibrary) -> Applicability | None:
    match ref.target:
        case SharedIcon(icon_id=icon_id):
            record = library.get_icon(icon_id)
            return record.metadata.applies_to if record is not None else None
        case _:
            return None


def _instance_names(
    instance_id: str, diagram_entities: Mapping[str, object], registry: ArtifactRegistry
) -> frozenset[str] | None:
    """The element's type and specialization names, where the instance can be classified generically."""
    if (entity := registry.get_entity(instance_id)) is not None:
        return entity.type_and_specializations
    for type_name, nodes in diagram_entities.items():
        if isinstance(nodes, list) and any(isinstance(n, Mapping) and n.get("id") == instance_id for n in nodes):
            return frozenset({str(type_name)})
    return None


def _error(code: str, message: str, loc: str) -> Issue:
    return Issue(Severity.ERROR, code, message, loc)


def _warning(code: str, message: str, loc: str) -> Issue:
    return Issue(Severity.WARNING, code, message, loc)
