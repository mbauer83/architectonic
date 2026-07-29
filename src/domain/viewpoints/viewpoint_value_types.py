"""Immutable query-result types, canonical syntax, and binding inference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from src.domain.ontology_representation.attribute_scales import ORDINAL_KIND
from src.domain.viewpoints.viewpoint_condition_validation import (
    CriteriaContext,
    RegistrySnapshot,
    resolve_attribute_path,
)
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    EntityCriteriaGroup,
    scalar_kinds_comparable,
)

ScalarKind = Literal["string", "integer", "number", "date", "boolean", "slug", "ordinal"]
BindingSelect = Literal["entities", "connections"]
AggregateKind = Literal["count", "sum", "avg", "min", "max"]

#: Every scalar kind, in one place, so parsing and coercion cannot drift apart.
SCALAR_KIND_NAMES: frozenset[str] = frozenset(
    {"string", "integer", "number", "date", "boolean", "slug", ORDINAL_KIND}
)


@dataclass(frozen=True)
class EntityInstanceType:
    type_slugs: frozenset[str]


@dataclass(frozen=True)
class ConnectionInstanceType:
    type_slugs: frozenset[str]


@dataclass(frozen=True)
class EntitySetType:
    type_slugs: frozenset[str]


@dataclass(frozen=True)
class ConnectionSetType:
    type_slugs: frozenset[str]


@dataclass(frozen=True)
class ScalarType:
    kind: ScalarKind


@dataclass(frozen=True)
class OptionalType:
    element: QueryResultType


@dataclass(frozen=True)
class ListType:
    element: QueryResultType


@dataclass(frozen=True)
class TupleType:
    elements: tuple[QueryResultType, ...]


QueryResultType: TypeAlias = (
    EntityInstanceType
    | ConnectionInstanceType
    | EntitySetType
    | ConnectionSetType
    | ScalarType
    | OptionalType
    | ListType
    | TupleType
)


class BindingTypeError(ValueError):
    """A stable-code type inference failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def format_result_type(value: QueryResultType) -> str:
    if isinstance(value, EntityInstanceType):
        return _slugged("entity", value.type_slugs)
    if isinstance(value, ConnectionInstanceType):
        return _slugged("connection", value.type_slugs)
    if isinstance(value, EntitySetType):
        return _slugged("entities", value.type_slugs)
    if isinstance(value, ConnectionSetType):
        return _slugged("connections", value.type_slugs)
    if isinstance(value, ScalarType):
        return value.kind
    if isinstance(value, OptionalType):
        return f"optional[{format_result_type(value.element)}]"
    if isinstance(value, ListType):
        return f"list[{format_result_type(value.element)}]"
    return f"tuple[{', '.join(format_result_type(item) for item in value.elements)}]"


def parse_result_type(raw: str) -> QueryResultType:
    if raw in SCALAR_KIND_NAMES:
        return ScalarType(cast(ScalarKind, raw))
    name, content = _bracketed(raw)
    if name in {"entity", "connection", "entities", "connections"}:
        types = frozenset(filter(None, content.split("|")))
        constructors = {
            "entity": EntityInstanceType,
            "connection": ConnectionInstanceType,
            "entities": EntitySetType,
            "connections": ConnectionSetType,
        }
        return constructors[name](types)
    if name == "optional":
        return OptionalType(parse_result_type(content))
    if name == "list":
        return ListType(parse_result_type(content))
    if name == "tuple":
        return TupleType(tuple(parse_result_type(part) for part in _split_top_level(content)))
    raise BindingTypeError("unknown-result-type", f"unknown result type {raw!r}")


def infer_binding_type(
    *,
    select: BindingSelect | None = None,
    criteria: EntityCriteriaGroup | ConnectionCriteriaGroup | None = None,
    input_type: QueryResultType | None = None,
    project: str | None = None,
    aggregate: AggregateKind | None = None,
    tuple_elements: tuple[QueryResultType, ...] = (),
    registries: RegistrySnapshot,
) -> QueryResultType:
    if tuple_elements:
        return TupleType(tuple_elements)
    if input_type is not None:
        inferred = input_type
    elif select is not None:
        inferred = _selection_type(select, criteria)
    else:
        raise BindingTypeError("binding-expression-missing", "binding requires a selection or tuple members")
    if project is not None:
        inferred = _project_type(inferred, project, registries)
    if aggregate is not None:
        inferred = _aggregate_type(inferred, aggregate)
    return inferred


def types_are_compatible(declared: QueryResultType, inferred: QueryResultType) -> bool:
    try:
        assert_types_are_compatible(declared, inferred)
    except BindingTypeError:
        return False
    return True


def assert_types_are_compatible(declared: QueryResultType, inferred: QueryResultType) -> None:
    if isinstance(declared, TupleType) and isinstance(inferred, TupleType):
        if len(declared.elements) != len(inferred.elements):
            raise BindingTypeError("tuple-arity-mismatch", "tuple values must have the same arity")
        for declared_element, inferred_element in zip(declared.elements, inferred.elements, strict=True):
            assert_types_are_compatible(declared_element, inferred_element)
        return
    if isinstance(declared, OptionalType) and isinstance(inferred, OptionalType):
        assert_types_are_compatible(declared.element, inferred.element)
        return
    if isinstance(declared, ListType) and isinstance(inferred, ListType):
        assert_types_are_compatible(declared.element, inferred.element)
        return
    if type(declared) is not type(inferred):
        compatible = (
            isinstance(declared, (EntityInstanceType, EntitySetType))
            and isinstance(inferred, (EntityInstanceType, EntitySetType))
            or isinstance(declared, (ConnectionInstanceType, ConnectionSetType))
            and isinstance(inferred, (ConnectionInstanceType, ConnectionSetType))
        )
        if not compatible:
            raise BindingTypeError("binding-type-mismatch", "declared and inferred result types differ")
        return
    if isinstance(declared, (EntityInstanceType, EntitySetType, ConnectionInstanceType, ConnectionSetType)):
        declared_slugs = _type_slugs(declared)
        inferred_slugs = _type_slugs(inferred)
        if not declared_slugs or not inferred_slugs or declared_slugs <= inferred_slugs:
            return
        raise BindingTypeError("binding-type-mismatch", "declared type union is incompatible with inference")
    if isinstance(declared, ScalarType) and isinstance(inferred, ScalarType):
        # Same string-like lattice the criteria comparators use: slug refines string.
        if not scalar_kinds_comparable(declared.kind, inferred.kind):
            raise BindingTypeError("binding-type-mismatch", "declared and inferred result types differ")
        return
    if declared != inferred:
        raise BindingTypeError("binding-type-mismatch", "declared and inferred result types differ")


def _selection_type(
    select: BindingSelect, criteria: EntityCriteriaGroup | ConnectionCriteriaGroup | None
) -> QueryResultType:
    slugs = _positive_type_slugs(criteria)
    return EntitySetType(slugs) if select == "entities" else ConnectionSetType(slugs)


def _positive_type_slugs(criteria: EntityCriteriaGroup | ConnectionCriteriaGroup | None) -> frozenset[str]:
    if criteria is None or criteria.negate or criteria.conjunction != "and":
        return frozenset()
    values: set[str] = set()
    for child in criteria.children:
        if isinstance(child, AttributeCondition):
            if child.attribute == "type" and not child.negate and child.comparator in {"eq", "in"}:
                literal = child.value.literal
                if isinstance(literal, str):
                    values.add(literal)
                elif isinstance(literal, (tuple, list)):
                    values.update(value for value in literal if isinstance(value, str))
        elif isinstance(child, (EntityCriteriaGroup, ConnectionCriteriaGroup)):
            values.update(_positive_type_slugs(child))
    return frozenset(values)


def _project_type(value: QueryResultType, path: str, registries: RegistrySnapshot) -> QueryResultType:
    projected = value.element if isinstance(value, OptionalType) else value
    context: CriteriaContext
    if isinstance(projected, (EntitySetType, EntityInstanceType)):
        context = "entity"
    elif isinstance(projected, (ConnectionSetType, ConnectionInstanceType)):
        context = "connection"
    else:
        raise BindingTypeError("projection-type-mismatch", "projection requires an entity or connection result")
    declared = resolve_attribute_path(path, context=context, registries=registries)
    if declared is None or (not _type_slugs(value) and declared != "reserved"):
        raise BindingTypeError("binding-attribute-type-ambiguous", f"cannot infer attribute {path!r}")
    kind: ScalarKind = "string" if declared == "reserved" else _scalar_kind(declared)
    scalar = ScalarType(kind)
    if isinstance(value, (EntityInstanceType, ConnectionInstanceType)):
        return scalar
    if isinstance(value, OptionalType):
        return OptionalType(scalar)
    return ListType(scalar)


def _aggregate_type(value: QueryResultType, aggregate: AggregateKind) -> ScalarType:
    if isinstance(value, (EntityInstanceType, ConnectionInstanceType, OptionalType)):
        raise BindingTypeError("aggregate-over-instance", "aggregates require a set or projected list")
    if aggregate == "count":
        return ScalarType("integer")
    element = value.element if isinstance(value, ListType) else None
    if not isinstance(element, ScalarType):
        raise BindingTypeError("aggregate-type-mismatch", "aggregate requires scalar values")
    if aggregate == "avg" and element.kind in {"integer", "number"}:
        return ScalarType("number")
    if aggregate == "sum" and element.kind in {"integer", "number"}:
        return element
    if aggregate in {"min", "max"} and element.kind in {"integer", "number", "date", ORDINAL_KIND}:
        # An ordinal reduces to one of its own members, never to the rank used to pick it: the
        # rank is an implementation detail of the ordering, and a position is not a value.
        return element
    if element.kind == ORDINAL_KIND:
        raise BindingTypeError(
            "aggregate-type-mismatch",
            f"{aggregate} cannot reduce an ordinal attribute: the distance between adjacent "
            "members is unknown, so a total or a mean of them denotes nothing. Use min or max "
            "to pick a member, or count to size the set.",
        )
    raise BindingTypeError("aggregate-type-mismatch", f"{aggregate} cannot reduce {element.kind}")


def _scalar_kind(raw: str) -> ScalarKind:
    return cast(ScalarKind, raw) if raw in SCALAR_KIND_NAMES else "string"


def _type_slugs(value: QueryResultType) -> frozenset[str]:
    if isinstance(value, (EntityInstanceType, EntitySetType, ConnectionInstanceType, ConnectionSetType)):
        return value.type_slugs
    if isinstance(value, OptionalType):
        return _type_slugs(value.element)
    return frozenset()


def _slugged(name: str, values: frozenset[str]) -> str:
    return f"{name}[{'|'.join(sorted(values))}]"


def _bracketed(raw: str) -> tuple[str, str]:
    if "[" not in raw or not raw.endswith("]"):
        raise BindingTypeError("invalid-result-type", f"invalid result type {raw!r}")
    name, content = raw.split("[", 1)
    return name, content[:-1]


def _split_top_level(raw: str) -> tuple[str, ...]:
    depth = 0
    start = 0
    parts: list[str] = []
    for index, char in enumerate(raw):
        depth += char == "["
        depth -= char == "]"
        if char == "," and depth == 0:
            parts.append(raw[start:index].strip())
            start = index + 1
    parts.append(raw[start:].strip())
    return tuple(part for part in parts if part)
