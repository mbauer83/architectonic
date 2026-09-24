"""A body carries the pictures its declarations show, in one block, and may show no other picture."""

from __future__ import annotations

import subprocess
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from src.application.puml_directive_policy import find_unsafe_puml_directives
from src.application.puml_icon_header import (
    BLOCK_BEGIN,
    BLOCK_END,
    embedded_icons,
    icon_key,
    icon_reference,
    referenced_icon_keys,
    with_icon_block,
)
from src.application.verification.artifact_verifier_syntax import find_plantuml_jar, plantuml_command
from src.domain.icons.render_form import render_digest
from tests.support.icon_files import png_of

BLUE = png_of((0, 120, 212, 255))
RED = png_of((220, 20, 20, 255))
K_BLUE, K_RED = icon_key(render_digest(BLUE)), icon_key(render_digest(RED))


def _body(*declarations: str) -> str:
    return "@startuml view\ntitle View\n" + "\n".join(declarations) + "\n@enduml\n"


def _showing(key: str, alias: str = "A") -> str:
    return f'rectangle "{icon_reference(key, "0.25")} {alias}" as {alias}'


def test_the_key_is_the_start_of_the_digest() -> None:
    assert K_BLUE == "ARCH_ICON_" + render_digest(BLUE).split(":")[1][:12]


def test_the_block_holds_each_referenced_picture_once_after_the_start_line() -> None:
    body = with_icon_block(_body(_showing(K_BLUE, "A"), _showing(K_BLUE, "B"), _showing(K_RED, "C")),
                           {K_BLUE: BLUE, K_RED: RED})

    lines = body.splitlines()
    assert lines[0] == "@startuml view" and lines[1] == BLOCK_BEGIN
    assert body.count(BLOCK_BEGIN) == body.count(BLOCK_END) == 1
    assert set(embedded_icons(body)) == {K_BLUE, K_RED}
    assert body.count("data:image/png;base64,") == 2


def test_rebuilding_is_idempotent_and_follows_the_references() -> None:
    once = with_icon_block(_body(_showing(K_BLUE), _showing(K_RED, "B")), {K_BLUE: BLUE, K_RED: RED})

    assert with_icon_block(once, {K_BLUE: BLUE, K_RED: RED}) == once
    dropped = once.replace(_showing(K_RED, "B") + "\n", "")
    assert set(embedded_icons(with_icon_block(dropped, {K_BLUE: BLUE, K_RED: RED}))) == {K_BLUE}


def test_a_body_that_draws_no_icon_carries_no_block() -> None:
    with_one = with_icon_block(_body(_showing(K_BLUE)), {K_BLUE: BLUE})

    plain = with_icon_block(with_one.replace(_showing(K_BLUE), 'rectangle "A" as A'), {K_BLUE: BLUE})

    assert BLOCK_BEGIN not in plain and referenced_icon_keys(plain) == frozenset()


def test_a_reference_whose_picture_is_not_known_stays_unembedded() -> None:
    body = with_icon_block(_body(_showing(K_RED)), {K_BLUE: BLUE})

    assert BLOCK_BEGIN not in body and referenced_icon_keys(body) == {K_RED}


def test_the_policy_allows_an_icon_the_body_embeds() -> None:
    assert find_unsafe_puml_directives(with_icon_block(_body(_showing(K_BLUE)), {K_BLUE: BLUE})) == []


@pytest.mark.parametrize(
    "tamper",
    [
        lambda b: b.replace(BLOCK_BEGIN + "\n", "").replace(BLOCK_END + "\n", ""),
        lambda b: b.replace("data:image/png;base64,", "/etc/passwd#"),
        lambda b: b.replace("@enduml", f'!${K_BLUE} = "/etc/passwd"\n@enduml'),
        lambda b: b.replace("title View", f'!${K_BLUE} = "data:image/png;base64,AAAA"\ntitle View'),
    ],
    ids=["block-markers-removed", "block-names-a-file", "reassigned-after-the-block", "assigned-outside"],
)
def test_an_icon_variable_given_any_other_value_or_place_is_refused(tamper) -> None:
    body = tamper(with_icon_block(_body(_showing(K_BLUE)), {K_BLUE: BLUE}))

    assert find_unsafe_puml_directives(body) != []


def test_a_reference_the_body_does_not_embed_is_refused() -> None:
    assert find_unsafe_puml_directives(_body(_showing(K_RED))) != []


@pytest.mark.skipif(find_plantuml_jar() is None, reason="PlantUML jar not provisioned")
@pytest.mark.parametrize("fmt", ["svg", "png"])
def test_the_sandboxed_renderer_draws_the_embedded_icon(tmp_path: Path, fmt: str) -> None:
    source = tmp_path / "view.puml"
    source.write_text(with_icon_block(_body(_showing(K_BLUE)), {K_BLUE: BLUE}), encoding="utf-8")
    jar = find_plantuml_jar()
    assert jar is not None

    subprocess.run(plantuml_command(jar, f"-t{fmt}", "-o", str(tmp_path), str(source)),
                   capture_output=True, timeout=120, check=True)

    output = (tmp_path / f"view.{fmt}").read_bytes()
    if fmt == "svg":
        assert b"data:image/png;base64," in output
    else:
        drawn = Image.open(BytesIO(output)).convert("RGBA").get_flattened_data()
        assert (0, 120, 212) in {pixel[:3] for pixel in drawn}
