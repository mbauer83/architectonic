"""A repository extends the shipped perspectives for its deployment, and coverage counts what it offers.

`.arch-repo/stress-perspectives.json` adds frameworks of its own and may put one in a shipped framework's
place; without it the shipped frameworks are offered as they are; a file that cannot be read as that shape
is refused, saying where, rather than skipped.
"""
import json
from pathlib import Path

import pytest

from src.domain.repository.repo_default_stress_perspectives import STRESS_PERSPECTIVES, unwritten_perspectives
from src.infrastructure.candidates.perspectives import UnreadablePerspectives, repository_perspectives


def _stating(root: Path, stated: object) -> Path:
    (root / ".arch-repo").mkdir(parents=True, exist_ok=True)
    (root / ".arch-repo" / "stress-perspectives.json").write_text(json.dumps(stated), encoding="utf-8")
    return root


_REGULATION = {"id": "regulation", "name": "Regulation", "perspectives": [
    {"name": "Data residency", "question": "What if data must stay in the country it was collected in?"},
]}


def test_without_a_file_the_shipped_frameworks_are_offered(tmp_path: Path) -> None:
    assert repository_perspectives(tmp_path) == STRESS_PERSPECTIVES


def test_a_framework_of_its_own_is_offered_after_the_shipped_ones(tmp_path: Path) -> None:
    offered = repository_perspectives(_stating(tmp_path, {"frameworks": [_REGULATION]}))

    assert [one.id for one in offered] == [*(one.id for one in STRESS_PERSPECTIVES), "regulation"]
    added = offered[-1].perspectives[0]
    assert (added.id, added.kind) == ("regulation.data-residency", "data residency")


def test_a_framework_with_a_shipped_id_takes_its_place(tmp_path: Path) -> None:
    own = {"id": "organisation", "name": "People", "perspectives": [
        {"name": "Works council", "question": "What if the works council vetoes the change?"},
    ]}

    offered = repository_perspectives(_stating(tmp_path, {"frameworks": [own]}))

    assert [one.id for one in offered] == [one.id for one in STRESS_PERSPECTIVES]
    assert [one.name for one in offered[-1].perspectives] == ["Works council"]


def test_coverage_counts_the_perspectives_the_repository_offers(tmp_path: Path) -> None:
    offered = repository_perspectives(_stating(tmp_path, {"frameworks": [_REGULATION]}))

    assert "regulation.data-residency" in unwritten_perspectives(["economic"], offered)
    assert "regulation.data-residency" not in unwritten_perspectives(["Data residency"], offered)


@pytest.mark.parametrize(("stated", "said"), [
    ([], "no list of frameworks"),
    ({"frameworks": [{"id": "x"}]}, "needs an id and a name"),
    ({"frameworks": [{"id": "x", "name": "X", "perspectives": []}]}, "lists no perspectives"),
    ({"frameworks": [{"id": "x", "name": "X", "perspectives": [{"name": "Y"}]}]}, "a name and a guiding question"),
])
def test_a_file_that_cannot_be_read_is_refused_saying_where(tmp_path: Path, stated: object, said: str) -> None:
    with pytest.raises(UnreadablePerspectives, match=said):
        repository_perspectives(_stating(tmp_path, stated))


def test_a_file_that_is_not_json_is_refused(tmp_path: Path) -> None:
    (tmp_path / ".arch-repo").mkdir()
    (tmp_path / ".arch-repo" / "stress-perspectives.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(UnreadablePerspectives, match="cannot be read as JSON"):
        repository_perspectives(tmp_path)
