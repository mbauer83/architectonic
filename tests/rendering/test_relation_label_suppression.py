"""Authored PUML bodies should drop relation-stereotype labels the arrow encodes.

Mirrors the auto-renderer rule (``show_stereotype``): labels are stripped only
for relation types with a distinctive arrow; UML-family flows that share the
generic arrow keep their disambiguating labels.
"""

from __future__ import annotations

from functools import lru_cache

from src.infrastructure.rendering.archimate_relation_rendering import strip_suppressed_relation_labels


@lru_cache(maxsize=1)
def _suppressed() -> frozenset[str]:
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry()).diagram_types.suppressed_stereotype_tokens()


def _strip(body: str) -> str:
    return strip_suppressed_relation_labels(body, _suppressed())


def test_archimate_relation_stereotypes_are_suppressed() -> None:
    tokens = _suppressed()
    assert {"influence", "realization", "association", "serving"} <= tokens


def test_strips_redundant_influence_and_realization_labels() -> None:
    body = (
        "DRV_GR9prv ..> ASS_CK90bp : <<influence>>\n"
        "OUT_AlZjX8 -up-|> GOL_5Fk9di : <<realization>>\n"
    )
    out = _strip(body)
    assert out == "DRV_GR9prv ..> ASS_CK90bp\nOUT_AlZjX8 -up-|> GOL_5Fk9di\n"


def test_keeps_association_and_multiplicity_and_element_lines() -> None:
    for line in (
        "ASS_CK90bp -- GOL_FCfDuc",
        "A --> B : 1 -> *",
        'rectangle "X" <<driver>> as DRV_x',
        "title Motivation Chain: From Drivers to Requirements",
    ):
        assert _strip(line) == line


def test_keeps_uml_family_labels_without_distinctive_arrow() -> None:
    # sequence/activity/er/usecase flows share the generic arrow → label is load-bearing.
    line = "A --> B : <<sequence-synchronous>>"
    assert _strip(line) == line


def test_strips_only_the_stereotype_keeping_free_text() -> None:
    line = "A ..> B : <<influence>> needs review"
    assert _strip(line) == "A ..> B : needs review"
