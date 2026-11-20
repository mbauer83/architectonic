"""The picture a syntax check renders is read before it is thrown away, and it is the right picture.

The checks on a rendered picture cost no render of their own: the syntax check already draws every
diagram to learn whether PlantUML accepts it. What that arrangement has to get right is *which*
picture belongs to which file — PlantUML names its output after the body's `@startuml`, not after
the file, so two diagrams of one name rendered into one directory overwrite each other, and a file
would be judged by another file's picture.

Runs PlantUML for real, through the `plantuml_syntax_check` fixture; skipped without plantuml.jar.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification._verifier_rules_rendered_picture import RenderedPictureRule
from src.application.verification.artifact_verifier_types import Issue, Severity
from src.infrastructure.rendering.layout.plantuml_svg_reader import read_rendered_picture
from src.infrastructure.verification.adapters import DefaultPumlSyntaxAdapter
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from tests.support.rendered_pictures import plantuml_available

_needs_plantuml = pytest.mark.skipif(
    not plantuml_available(), reason="plantuml.jar not found — skipping rendered-picture assertions"
)


class _Recording:
    """Stands where the picture checks stand, and keeps what it was handed."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def check(self, svg: str, loc: str) -> list[Issue]:
        self.seen.append(svg)
        return [Issue(Severity.WARNING, "W371", "a finding about this picture", loc, details={"picture": svg})]


def _picture_reported(issues: list[Issue]) -> str:
    assert [issue.code for issue in issues] == ["W371"], issues
    details = issues[0].details
    assert details is not None
    return str(details["picture"])


def _diagram(directory: Path, file_name: str, label: str, *, startuml: str = "one-name") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / file_name
    path.write_text(f'@startuml {startuml}\nrectangle "{label}" as A\n@enduml\n', encoding="utf-8")
    return path


def test_the_factory_gives_the_syntax_port_the_picture_checks() -> None:
    """Without this a verifier renders every picture and reads none, and reports them all clean."""
    from src.infrastructure.app_bootstrap import process_runtime_catalogs

    verifier = build_artifact_verifier(catalogs=process_runtime_catalogs())
    port = verifier._puml_port

    assert isinstance(port, DefaultPumlSyntaxAdapter)
    assert port._picture_checks == RenderedPictureRule(read=read_rendered_picture)


def test_a_verifier_that_may_not_start_a_subprocess_checks_no_picture() -> None:
    from src.infrastructure.app_bootstrap import process_runtime_catalogs

    assert build_artifact_verifier(catalogs=process_runtime_catalogs(), check_puml_syntax=False)._puml_port is None


@_needs_plantuml
@pytest.mark.usefixtures("plantuml_syntax_check")
class TestWithPlantUml:
    def test_two_diagrams_of_one_name_in_one_folder_are_each_judged_by_their_own_picture(self, tmp_path: Path) -> None:
        folder = tmp_path / "diagram-catalog" / "diagrams"
        first = _diagram(folder, "ARC@1.a.first.puml", "Only In The First")
        second = _diagram(folder, "ARC@2.b.second.puml", "Only In The Second")
        checks = _Recording()

        found = DefaultPumlSyntaxAdapter(checks).check_batch([first, second])

        assert len(checks.seen) == 2  # noqa: PLR2004 — one picture each, neither overwritten by the other
        of_first, of_second = _picture_reported(found[first]), _picture_reported(found[second])
        assert "First" in of_first and "Second" not in of_first
        assert "Second" in of_second and "First" not in of_second
        assert {path: [issue.location for issue in issues] for path, issues in found.items()} == {
            first: [str(first)], second: [str(second)],
        }

    def test_nothing_is_written_beside_the_diagrams(self, tmp_path: Path) -> None:
        folder = tmp_path / "diagram-catalog" / "diagrams"
        diagram = _diagram(folder, "ARC@1.a.first.puml", "A")
        before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

        DefaultPumlSyntaxAdapter(_Recording()).check_batch([diagram])
        DefaultPumlSyntaxAdapter(_Recording()).check_one(diagram, str(diagram))

        assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before

    def test_a_single_check_reads_its_one_picture(self, tmp_path: Path) -> None:
        diagram = _diagram(tmp_path, "ARC@1.a.first.puml", "Alone")
        checks = _Recording()

        issues = DefaultPumlSyntaxAdapter(checks).check_one(diagram, "where the caller said")

        assert len(checks.seen) == 1
        assert "Alone" in _picture_reported(issues)
        assert issues[0].location == "where the caller said"

    def test_a_body_plantuml_refuses_is_an_error_about_the_file_and_no_picture_is_read(self, tmp_path: Path) -> None:
        broken = tmp_path / "ARC@1.a.broken.puml"
        broken.write_text("@startuml broken\nthis is not plantuml ((\n@enduml\n", encoding="utf-8")
        fine = _diagram(tmp_path / "other", "ARC@2.b.fine.puml", "Fine")
        checks = _Recording()

        found = DefaultPumlSyntaxAdapter(checks).check_batch([broken, fine])

        assert [issue.code for issue in found[broken]] == ["E350"]
        assert found[broken][0].location == str(broken)
        assert "arch-syntax-" not in found[broken][0].message, "the copy PlantUML was shown is not the author's file"
        assert len(checks.seen) == 1 and "Fine" in _picture_reported(found[fine])

    def test_the_real_checks_find_nothing_wrong_with_a_plain_picture(self, tmp_path: Path) -> None:
        diagram = tmp_path / "ARC@1.a.plain.puml"
        diagram.write_text(
            '@startuml plain\nrectangle "Group" as G {\n  rectangle "Alpha" as A\n  rectangle "Beta" as B\n}\n'
            "A --> B : serves\n@enduml\n",
            encoding="utf-8",
        )
        adapter = DefaultPumlSyntaxAdapter(RenderedPictureRule(read=read_rendered_picture))

        assert adapter.check_one(diagram, str(diagram)) == []
        assert adapter.check_batch([diagram]) == {diagram: []}

    def test_a_sequence_chart_is_not_a_picture_the_checks_speak_of(self, tmp_path: Path) -> None:
        chart = tmp_path / "SEQ@1.a.chart.puml"
        chart.write_text("@startuml chart\nAlice -> Bob : hello\n@enduml\n", encoding="utf-8")

        adapter = DefaultPumlSyntaxAdapter(RenderedPictureRule(read=read_rendered_picture))

        assert adapter.check_one(chart, str(chart)) == []
