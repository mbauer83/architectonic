"""A reference names a library icon or a diagram-local one, in either written form, and nothing else."""

from __future__ import annotations

import pytest

from src.domain.icons.icon_ref import (
    IconRef,
    InvalidIconRefError,
    LocalIcon,
    SharedIcon,
    icon_ref_from,
)
from src.domain.icons.render_form import render_digest


def test_a_library_icon_is_named_by_its_rename_stable_id() -> None:
    assert icon_ref_from("ICO@1790000000.Ab_c-1.azure-aks") == IconRef(SharedIcon("ICO@1790000000.Ab_c-1"))


def test_a_local_icon_is_named_by_its_key() -> None:
    assert icon_ref_from("local:rabbit") == IconRef(LocalIcon("rabbit"))


def test_the_bare_and_the_mapping_form_read_to_the_same_value_when_no_style_is_given() -> None:
    assert icon_ref_from({"icon": "local:rabbit"}) == icon_ref_from("local:rabbit")


@pytest.mark.parametrize(
    "ref",
    [IconRef(SharedIcon("ICO@1.abc")), IconRef(LocalIcon("k8s"), "figure"), IconRef(SharedIcon("ICO@1.abc"), "badge")],
)
def test_a_reference_round_trips_through_its_stored_form(ref: IconRef) -> None:
    assert icon_ref_from(ref.as_stored()) == ref


@pytest.mark.parametrize(
    "raw",
    [
        "APP@1790000000.abc",
        "local:",
        "local:Upper",
        "local:a--b",
        "local:-lead",
        "local:" + "a" * 49,
        "icon.png",
        {"icon": "local:x", "style": "sticker"},
        {"icon": "local:x", "scale": 2},
        {"style": "badge"},
        42,
    ],
)
def test_anything_else_is_refused(raw: object) -> None:
    with pytest.raises(InvalidIconRefError):
        icon_ref_from(raw)


def test_a_digest_names_the_stored_bytes() -> None:
    digest = render_digest(b"\x89PNG")

    assert digest.startswith("sha256:") and len(digest) == len("sha256:") + 64
    assert digest != render_digest(b"\x89PNH")
