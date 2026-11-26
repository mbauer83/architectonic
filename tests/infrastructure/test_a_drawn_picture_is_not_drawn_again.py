"""A source PlantUML drew once is not drawn again: the picture is handed back (`plantuml_pictures`).

Saving an arrangement of a large diagram drew the same body three times — when the editor read it, to
verify the write, for the rendered outputs — at about seven seconds a drawing on a 259-element view, and
arranging changes only the layout block, which PlantUML never reads. What has to hold is that only the
same source is handed the same picture: another body, another setting, a refusal, or a body that names a
file is drawn (or refused) afresh.

Runs PlantUML for real; skipped without plantuml.jar.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.plantuml_pictures import DrawnPictures, picture_key
from src.application.verification import artifact_verifier_syntax
from src.application.verification.artifact_verifier_types import Issue
from src.infrastructure.rendering import puml_runtime
from tests.support.rendered_pictures import plantuml_available

_needs_plantuml = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")


class _Counting:
    """`subprocess` as a module uses it, counting the PlantUML runs it starts."""

    def __init__(self, real: object) -> None:
        self._real = real
        self.runs = 0

    def run(self, *args: object, **kwargs: object) -> object:
        self.runs += 1
        return self._real.run(*args, **kwargs)  # type: ignore[attr-defined]

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


class _Recording:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def check(self, svg: str, loc: str) -> list[Issue]:
        del loc
        self.seen.append(svg)
        return []


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return tmp_path


class TestTheStore:
    def test_keeps_the_most_recently_asked_within_its_capacity(self) -> None:
        drawn = DrawnPictures(capacity=2)
        drawn.keep("a", b"A")
        drawn.keep("b", b"B")
        assert drawn.recall("a") == b"A"
        drawn.keep("c", b"C")

        assert (drawn.recall("a"), drawn.recall("b"), drawn.recall("c")) == (b"A", None, b"C")

    def test_a_source_that_names_a_file_has_no_key(self) -> None:
        assert picture_key("@startuml\n!include x.puml\n@enduml", jar=None, dot=None, java="java") is None
        one = picture_key("@startuml\nA -> B\n@enduml", "-tsvg", jar=None, dot=None, java="java")
        assert one is not None
        assert one != picture_key("@startuml\nA -> B\n@enduml", "-tpng", jar=None, dot=None, java="java")


@_needs_plantuml
class TestARender:
    def test_draws_a_body_once_and_another_body_again(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        counting = _Counting(puml_runtime.subprocess)
        monkeypatch.setattr(puml_runtime, "subprocess", counting)
        repo = _repo(tmp_path)
        body = '@startuml\nrectangle "One" as A\n@enduml\n'

        first, _ = puml_runtime.render_puml_svg(body, repo)
        again, _ = puml_runtime.render_puml_svg(body, repo)
        other, _ = puml_runtime.render_puml_svg(body.replace("One", "Two"), repo)

        assert first is not None and again == first
        assert other is not None and other != first
        assert counting.runs == 2

    def test_draws_a_refused_body_again(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        counting = _Counting(puml_runtime.subprocess)
        monkeypatch.setattr(puml_runtime, "subprocess", counting)
        repo = _repo(tmp_path)
        broken = "@startuml\nthis is not plantuml ][\n@enduml\n"

        puml_runtime.render_puml_bytes(broken, repo, "svg", None)
        puml_runtime.render_puml_bytes(broken, repo, "svg", None)

        assert counting.runs == 2


@_needs_plantuml
@pytest.mark.usefixtures("plantuml_syntax_check")
class TestTheSyntaxCheck:
    def test_draws_one_diagram_once_whatever_its_frontmatter_says(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A layout written into the frontmatter is not read by PlantUML, nor is where the verifier copied the
        file to: the picture is the one drawn."""
        counting = _Counting(artifact_verifier_syntax.subprocess)
        monkeypatch.setattr(artifact_verifier_syntax, "subprocess", counting)
        path = tmp_path / "diagram.puml"
        body = '@startuml one\nrectangle "One" as A\n@enduml\n'
        checks = _Recording()

        path.write_text(f"---\nname: before\n---\n{body}", encoding="utf-8")
        artifact_verifier_syntax.check_puml_syntax(path, str(path), picture_checks=checks)
        # As the verifier checks a write: a copy in a directory of its own each time.
        copy = tmp_path / "elsewhere" / "diagram.puml"
        copy.parent.mkdir()
        copy.write_text(f"---\nname: after\nlayout: {{}}\n---\n{body}", encoding="utf-8")
        artifact_verifier_syntax.check_puml_syntax(copy, str(copy), picture_checks=checks)
        path.write_text(f"---\nname: after\n---\n{body.replace('One', 'Two')}", encoding="utf-8")
        artifact_verifier_syntax.check_puml_syntax(path, str(path), picture_checks=checks)

        assert counting.runs == 2
        assert len(checks.seen) == 3
        assert checks.seen[0] == checks.seen[1] != checks.seen[2]
