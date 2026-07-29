"""Scale-style evaluation and validation contracts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_evaluation_context import CriteriaReadAccess, EvaluationEnvironment
from src.domain.viewpoints.viewpoint_presentation_validation import validate_presentation
from src.domain.viewpoints.viewpoint_scale_styling import (
    ScaleBounds,
    ScaleStyleValue,
    StyleValue,
    calculate_scale_bounds,
)
from src.domain.viewpoints.viewpoint_style_evaluation import Item, ItemKind, evaluate_item_style
from src.domain.viewpoints.viewpoints import PresentationSpec, StyleRule


def _style_and_drift(
    item: Item,
    item_kind: ItemKind,
    presentation: PresentationSpec | None,
    *,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
    environment: EvaluationEnvironment = EvaluationEnvironment(),
    scale_bounds: Mapping[int, ScaleBounds] = {},
) -> tuple[Mapping[str, StyleValue], frozenset[str]]:
    evaluation = evaluate_item_style(
        item,
        item_kind,
        presentation,
        read_access=read_access,
        registries=registries,
        environment=environment,
        scale_bounds=scale_bounds,
    )
    return evaluation.style, evaluation.schema_drift


def _entity(identifier: str, score: int | None, *, specializations: tuple[str, ...] = ()) -> EntityRecord:
    extra: dict[str, object] = {} if score is None else {"score": score}
    return EntityRecord(
        artifact_id=identifier,
        artifact_type="application-component",
        name=identifier,
        version="1",
        status="draft",
        domain="application",
        subdomain="",
        path=Path("/fake/entity.md"),
        keywords=(),
        extra=extra,
        content_text="",
        display_blocks={},
        display_label=identifier,
        display_alias="",
        specializations=specializations,
    )


_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"application-component"}),
    known_connection_types=frozenset(),
    known_specialization_slugs=frozenset(),
    entity_attribute_types={"score": "number"},
    connection_attribute_types={},
)


def _presentation(**overrides: object) -> PresentationSpec:
    fields: dict[str, object] = {
        "capability": "node_color",
        "mode": "scale",
        "scale_attribute": "score",
        "scale_tokens": ("#00ffff", "#ff8800"),
    }
    fields.update(overrides)
    rule = StyleRule(**fields)  # type: ignore[arg-type]
    return PresentationSpec(
        representation="exploration",
        styling_rules=(rule,),
        default_style={"node_color": "neutral"},
    )


def test_data_driven_scale_bounds_are_order_independent_and_emit_legend() -> None:
    low, high = _entity("low", 10), _entity("high", 30)
    presentation = _presentation()
    bounds, legends, drift = calculate_scale_bounds(
        presentation,
        ((high, "entity"), (low, "entity")),
        registries=_REGISTRIES,
        environment=EvaluationEnvironment(),
    )

    assert bounds[0].minimum == 10
    assert bounds[0].maximum == 30
    assert legends[0].tokens == ("#00ffff", "#ff8800")
    assert drift == frozenset()
    style, _ = _style_and_drift(
        low,
        "entity",
        presentation,
        read_access=_EmptyGraph(),
        registries=_REGISTRIES,
        scale_bounds=bounds,
    )
    assert style == {"node_color": ScaleStyleValue(position=0.0, tokens=("#00ffff", "#ff8800"))}


def test_scale_applies_to_matches_any_specialization_not_only_the_primary() -> None:
    # WU-V3: a scale scoped to a concept's SECOND specialization still applies to it.
    entity = _entity("multi", 20, specializations=("service", "audited"))
    presentation = _presentation(applies_to=frozenset({"audited"}))
    bounds, _, _ = calculate_scale_bounds(
        presentation, ((entity, "entity"),), registries=_REGISTRIES, environment=EvaluationEnvironment(),
    )
    style, _ = _style_and_drift(
        entity, "entity", presentation, read_access=_EmptyGraph(), registries=_REGISTRIES, scale_bounds=bounds,
    )
    assert isinstance(style["node_color"], ScaleStyleValue)


def test_missing_scale_value_uses_default_style_and_out_of_range_saturates() -> None:
    missing, below, above = _entity("missing", None), _entity("below", 5), _entity("above", 50)
    presentation = _presentation(scale_min=10, scale_max=30)
    bounds, _, _ = calculate_scale_bounds(
        presentation,
        ((missing, "entity"), (below, "entity"), (above, "entity")),
        registries=_REGISTRIES,
        environment=EvaluationEnvironment(),
    )

    def style_for(entity: EntityRecord) -> object:
        style, _ = _style_and_drift(
            entity,
            "entity",
            presentation,
            read_access=_EmptyGraph(),
            registries=_REGISTRIES,
            scale_bounds=bounds,
        )
        return style["node_color"]

    assert style_for(missing) == "neutral"
    # Out-of-range values clamp to the nearest endpoint instead of dropping out of the scale.
    assert style_for(below) == ScaleStyleValue(position=0.0, tokens=("#00ffff", "#ff8800"))
    assert style_for(above) == ScaleStyleValue(position=1.0, tokens=("#00ffff", "#ff8800"))


def test_scale_validation_rejects_mixed_mode_fields_and_wrong_token_count() -> None:
    presentation = _presentation(value="emphasis", scale_tokens=("heat-near",))
    issues = validate_presentation(presentation, path="/presentation", registries=_REGISTRIES, check_ergonomics=True)

    assert {(issue.code, issue.path) for issue in issues} == {
        ("style-mode-field-mismatch", "/presentation/styling_rules/0"),
        ("scale-token-count", "/presentation/styling_rules/0/scale_tokens"),
    }


def test_scale_validation_rejects_a_derived_reference_the_query_never_declares() -> None:
    presentation = _presentation(scale_attribute="derived.conn_count")
    issues = validate_presentation(
        presentation,
        path="/presentation",
        registries=_REGISTRIES,
        check_ergonomics=True,
        declared_derived_names=frozenset({"impact-distance"}),
    )
    assert [(issue.severity, issue.code, issue.path) for issue in issues] == [
        ("error", "unknown-attribute", "/presentation/styling_rules/0/scale_attribute")
    ]
    assert "conn_count" in issues[0].message


def test_scale_validation_accepts_a_declared_derived_reference() -> None:
    presentation = _presentation(scale_attribute="derived.impact-distance")
    issues = validate_presentation(
        presentation,
        path="/presentation",
        registries=_REGISTRIES,
        check_ergonomics=True,
        declared_derived_names=frozenset({"impact-distance"}),
    )
    assert issues == []


class _EmptyGraph:
    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return None

    def find_connections_for(
        self, entity_id: str, *, direction: str = "any", conn_type: str | None = None
    ) -> list[object]:
        return []
