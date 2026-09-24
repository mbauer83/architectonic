"""An icon file reads back exactly what was written, over everything the format permits."""

from __future__ import annotations

import itertools

import pytest

from src.domain.icons.applicability import applicability_from
from src.domain.icons.icon_file import (
    IconFile,
    IconFileProblem,
    IconMetadata,
    format_icon_file,
    read_icon_file,
)
from src.domain.icons.render_form import render_digest

PNG = bytes(range(256)) * 3  # long enough to wrap, and every byte value


def _icon(**overrides: object) -> IconFile:
    fields: dict[str, object] = {
        "artifact_id": "ICO@1790000000.Ab_c-1.azure-kubernetes-service",
        "name": "Azure Kubernetes Service",
        "source_format": "svg",
        "width": 128,
        "height": 96,
        "render_digest": render_digest(PNG),
        "attribution": "Microsoft Azure architecture icons, used under the Microsoft terms",
        "applies_to": applicability_from(["kubernetes-cluster"]),
        "default_style": "badge",
        "tags": ("azure", "compute"),
        "status": "active",
        "last_updated": "2026-09-24T12:00:00Z",
    }
    svg = overrides.pop("svg_source", '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1"/></svg>')
    fields.update(overrides)
    return IconFile(IconMetadata(**fields), PNG, svg)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("style", "status", "source_format"),
    list(itertools.product(("badge", "figure"), ("active", "retired"), ("svg", "png", "jpeg", "webp"))),
)
def test_every_style_status_and_source_format_round_trips(style: str, status: str, source_format: str) -> None:
    icon = _icon(default_style=style, status=status, source_format=source_format,
                 svg_source=None if source_format != "svg" else "<svg/>")

    assert read_icon_file(format_icon_file(icon)) == icon


@pytest.mark.parametrize(
    "overrides",
    [
        {"applies_to": applicability_from([])},
        {"tags": ()},
        {"name": "Zürich — Rechenzentrum «Nord»"},
        {"attribution": "Logo: ACME, Inc.: used with permission; see https://example.invalid/#terms"},
        {"svg_source": None},
    ],
    ids=["unrestricted", "untagged", "unicode-name", "punctuated-attribution", "raster-only"],
)
def test_the_optional_and_awkward_values_round_trip(overrides: dict[str, object]) -> None:
    icon = _icon(**overrides)

    assert read_icon_file(format_icon_file(icon)) == icon


def test_a_key_a_later_release_adds_is_ignored() -> None:
    written = format_icon_file(_icon()).replace("status: active", "status: active\nfuture-key: 1")

    assert read_icon_file(written) == _icon()


@pytest.mark.parametrize(
    ("damage", "reason"),
    [
        (lambda t: t.replace("artifact-type: icon", "artifact-type: entity"), "artifact-type"),
        (lambda t: t.replace("width: 128", "width: 0"), "width"),
        (lambda t: t.replace("default-style: badge", "default-style: sticker"), "default-style"),
        (lambda t: t.replace("status: active", "status: gone"), "status"),
        (lambda t: t.replace("```png-base64", "```png"), "png-base64"),
        (lambda t: t.replace(t.split("```png-base64\n")[1][:4], "!!!!"), "not base64"),
        (lambda t: t.replace("- kubernetes-cluster", "- ''"), "applies-to"),
        (lambda t: t.split("---\n\n", 1)[1], "frontmatter"),
    ],
    ids=["wrong-type", "zero-width", "unknown-style", "unknown-status", "no-png-block", "bad-base64",
         "empty-applicability", "no-frontmatter"],
)
def test_a_file_whose_shape_cannot_be_stated_says_why(damage, reason: str) -> None:
    result = read_icon_file(damage(format_icon_file(_icon())))

    assert isinstance(result, IconFileProblem) and reason in result.reason, result
