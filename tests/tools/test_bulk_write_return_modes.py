"""What `artifact_bulk_write` answers, and how much of it.

The caller of this surface is usually an agent, so a reply's size is part of its contract. Before
`return_mode`, a fifty-item batch answered with fifty objects that each repeated the batch's
`operation_id` and carried an absolute path derivable from the artifact id — and none of them echoed
the `_ref` alias the caller had used, so correlating an alias to its allocated id meant trusting input
order to survive the documented auto-sort. The alias map is the one thing most callers need from a
successful create, and it was the one thing the reply did not state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from src.infrastructure.mcp.artifact_mcp.bulk_tools import artifact_bulk_write


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A bare engagement repository, as `test_bulk_write` builds one."""
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


_CREATES = [
    {"op": "create_entity", "artifact_type": "requirement", "name": "Alpha", "_ref": "alpha"},
    {"op": "create_entity", "artifact_type": "requirement", "name": "Beta", "_ref": "beta"},
    {
        "op": "add_connection",
        "source_entity": "$ref:alpha",
        "connection_type": "archimate-association",
        "target_entity": "$ref:beta",
    },
]


def _write(repo: Path, items: list[dict[str, Any]], **kwargs: Any) -> dict[str, object]:
    return artifact_bulk_write(items=items, dry_run=False, repo_root=str(repo), **kwargs)


def _items(payload: dict[str, object]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], payload["items"])


# ── The alias map ─────────────────────────────────────────────────────────────


def test_every_alias_is_echoed_against_the_id_it_was_allocated(repo: Path) -> None:
    payload = _write(repo, list(_CREATES))

    refs = cast(dict[str, str], payload["refs"])
    assert sorted(refs) == ["alpha", "beta"]
    assert all(value.startswith("REQ@") for value in refs.values()), refs


def test_the_alias_map_is_available_without_asking_for_any_items(repo: Path) -> None:
    """`ids` is for the caller that only needs to know what its aliases became."""
    payload = _write(repo, list(_CREATES), return_mode="ids")

    assert sorted(cast(dict[str, str], payload["refs"])) == ["alpha", "beta"]
    assert _items(payload) == []


def test_the_alias_map_agrees_with_the_ids_the_items_report(repo: Path) -> None:
    """Correlation by alias and correlation by position must not be able to disagree."""
    payload = _write(repo, list(_CREATES), return_mode="full")

    refs = cast(dict[str, str], payload["refs"])
    created = [item for item in _items(payload) if item["op"] == "create_entity"]
    assert [refs["alpha"], refs["beta"]] == [item["artifact_id"] for item in created]


def test_a_batch_with_no_aliases_reports_an_empty_map_rather_than_omitting_it(repo: Path) -> None:
    payload = _write(repo, [{"op": "create_entity", "artifact_type": "requirement", "name": "Solo"}])

    assert payload["refs"] == {}


# ── What each mode carries ────────────────────────────────────────────────────


def test_a_clean_batch_summarises_to_no_items_at_all(repo: Path) -> None:
    """The default. Fifty clean creates answer with their counts and their aliases."""
    payload = _write(repo, list(_CREATES))

    assert payload["return_mode"] == "summary"
    assert _items(payload) == []
    assert payload["item_count"] == 3
    assert payload["failed_count"] == 0
    assert payload["counts"] == {"create_entity": 2, "add_connection": 1}


def test_full_lists_every_item_in_input_order(repo: Path) -> None:
    payload = _write(repo, list(_CREATES), return_mode="full")

    assert [item["op"] for item in _items(payload)] == ["create_entity", "create_entity", "add_connection"]


def test_summary_keeps_the_items_that_have_something_to_report(repo: Path) -> None:
    """A failed batch rolls back whole, so every item has something to report — including the one
    that applied during staging and was then undone. Reporting only the item that broke would leave a
    caller believing its other creates had landed."""
    payload = _write(
        repo,
        [
            {"op": "create_entity", "artifact_type": "requirement", "name": "Fine"},
            {"op": "edit_entity", "artifact_id": "REQ@1.nosuch", "name": "Nope"},
        ],
    )

    reported = _items(payload)
    assert [item["op"] for item in reported] == ["create_entity", "edit_entity"]
    assert "Rolled back" in str(reported[0]["error"])
    assert "not found in model" in str(reported[1]["error"])
    assert payload["committed"] is False
    assert payload["failed_count"] == 2, "every item carries an error once the batch rolls back"


def test_counts_cover_every_item_whatever_the_mode_shows(repo: Path) -> None:
    """The counts are the batch's, not the shown items' — otherwise summary would undercount."""
    payload = _write(repo, list(_CREATES), return_mode="ids")

    assert payload["counts"] == {"create_entity": 2, "add_connection": 1}
    assert payload["item_count"] == 3


# ── What the batch says once instead of per item ───────────────────────────────


def test_the_operation_id_is_stated_once_for_the_batch(repo: Path) -> None:
    payload = _write(repo, list(_CREATES), return_mode="full")

    assert isinstance(payload["operation_id"], str)
    assert all("operation_id" not in item for item in _items(payload))


def test_the_derivable_path_is_dropped_from_the_compact_modes(repo: Path) -> None:
    """The longest field per item, and reconstructible from the id, the group and the type."""
    full = _write(repo, [{"op": "create_entity", "artifact_type": "requirement", "name": "Pathful"}],
                  return_mode="full")
    summary = _write(
        repo,
        [
            {"op": "create_entity", "artifact_type": "requirement", "name": "Warned"},
            {"op": "edit_entity", "artifact_id": "REQ@1.nosuch", "name": "Nope"},
        ],
    )

    assert "path" in _items(full)[0]
    assert all("path" not in item for item in _items(summary))


@pytest.mark.parametrize("return_mode", ["summary", "full", "ids"])
def test_every_mode_answers_with_the_same_shape(repo: Path, return_mode: str) -> None:
    """A caller must not have to branch on the mode to find the ids."""
    payload = _write(repo, list(_CREATES), return_mode=return_mode)

    assert set(payload) == {
        "operation_id",
        "dry_run",
        "committed",
        "item_count",
        "failed_count",
        "counts",
        "refs",
        "return_mode",
        "items",
    }


def test_a_dry_run_says_so_and_commits_nothing(repo: Path) -> None:
    payload = artifact_bulk_write(items=list(_CREATES), dry_run=True, repo_root=str(repo))

    assert payload["dry_run"] is True
    assert payload["committed"] is False


# ── Replay ────────────────────────────────────────────────────────────────────


def test_a_replayed_batch_can_be_asked_for_a_different_level_of_detail(repo: Path) -> None:
    """An idempotency key names one logical batch, not one verbosity."""
    key = "return-mode-replay"
    first = _write(repo, list(_CREATES), idempotency_key=key, return_mode="ids")
    replayed = _write(repo, list(_CREATES), idempotency_key=key, return_mode="full")

    assert first["operation_id"] == replayed["operation_id"]
    assert _items(first) == []
    assert len(_items(replayed)) == 3
    assert replayed["refs"] == first["refs"]


def test_an_unknown_op_still_answers_with_the_batch_envelope(repo: Path) -> None:
    payload = _write(repo, [{"op": "not_an_op", "name": "X"}], return_mode="full")

    assert payload["failed_count"] == 1
    assert payload["counts"] == {"not_an_op": 1}
    assert _items(payload)[0]["error"]
