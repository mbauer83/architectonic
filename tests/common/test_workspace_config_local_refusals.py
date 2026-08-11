"""A malformed `local:` in `arch-workspace.yaml` is refused by name, not by traceback.

`configured_repo_path` hands `spec["local"]` to `Path()`. A non-string there raised a raw `TypeError`
at startup, where every other mistake in this file gets a named `ERROR:` line — a first-run papercut
in the one file a new user must write by hand.

The blank string is refused for a different reason: `Path("")` is `.`, which resolves to the workspace
root, so the whole workspace would be treated as the repository rather than the configuration being
rejected.

Every spec is authored here, so exact assertions are the test's own.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.config.workspace_paths import (
    _validate_repo_spec,
    configured_engagements,
    configured_repo_path,
    parse_workspace_config,
)

#: Shapes a YAML author produces by accident. `None` is a bare `local:` with nothing after it — the
#: likeliest of them, and the one that reached `Path(None)`.
MALFORMED_LOCAL = [
    pytest.param(None, id="bare-key"),
    pytest.param("", id="empty-string"),
    pytest.param("   ", id="whitespace-only"),
    pytest.param(["repos/engagement"], id="yaml-list"),
    pytest.param({"path": "repos/engagement"}, id="yaml-mapping"),
    pytest.param(42, id="number"),
]


class TestValidateRepoSpec:
    @pytest.mark.parametrize("local", MALFORMED_LOCAL)
    def test_it_refuses_a_local_that_does_not_name_a_path(self, local: object) -> None:
        with pytest.raises(SystemExit) as refusal:
            _validate_repo_spec({"local": local}, label="engagement")

        assert str(refusal.value) == "ERROR: engagement.local must be a non-empty string"

    def test_the_refusal_names_the_offending_entry(self) -> None:
        """The label is what makes the message actionable when several engagements are configured."""
        with pytest.raises(SystemExit) as refusal:
            _validate_repo_spec({"local": None}, label="engagements.available.ENG-OTHER")

        assert "engagements.available.ENG-OTHER.local" in str(refusal.value)

    def test_a_string_local_is_accepted_unchanged(self) -> None:
        spec = {"local": "repos/engagement"}
        assert _validate_repo_spec(spec, label="engagement") == spec

    def test_a_git_spec_is_unaffected(self) -> None:
        """The `local` check must not fire on the sibling branch, which has its own rule."""
        spec = {"git": {"url": "git@example.invalid:org/repo.git", "path": "repos/enterprise"}}
        assert _validate_repo_spec(spec, label="enterprise") == spec


def _workspace_config(tmp_path: Path, local: object) -> Path:
    """An otherwise valid workspace config whose engagement `local` is `local`."""
    config = {
        "enterprise": {"local": "enterprise-repository"},
        "engagement": {"local": local},
    }
    path = tmp_path / "arch-workspace.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


class TestRegressionThroughTheFileTheUserWrites:
    """The reported path: a hand-written config file, parsed at startup."""

    @pytest.mark.parametrize("local", MALFORMED_LOCAL)
    def test_parsing_the_file_refuses_rather_than_raising_typeerror(
        self, tmp_path: Path, local: object
    ) -> None:
        """`SystemExit` is the whole assertion, because the regression raises `TypeError`.

        `pytest.raises(SystemExit)` does not catch a `TypeError`, so removing the guard fails this
        test rather than passing it on a different error — which is what the original defect was: an
        unhandled traceback at startup instead of a named refusal.
        """
        with pytest.raises(SystemExit) as refusal:
            parse_workspace_config(_workspace_config(tmp_path, local))

        assert str(refusal.value) == "ERROR: engagement.local must be a non-empty string"

    def test_a_well_formed_config_still_parses(self, tmp_path: Path) -> None:
        config = parse_workspace_config(_workspace_config(tmp_path, "repos/engagement"))

        assert config["engagement"] == {"local": "repos/engagement"}
        assert configured_repo_path(config["engagement"], tmp_path) == tmp_path / "repos/engagement"

    def test_an_engagements_available_entry_is_validated_too(self, tmp_path: Path) -> None:
        """`configured_engagements` is the other route into the same check."""
        with pytest.raises(SystemExit) as refusal:
            configured_engagements(
                {"engagements": {"available": {"ENG-A": {"local": None}}}}
            )

        assert str(refusal.value) == "ERROR: engagements.available.ENG-A.local must be a non-empty string"


class TestConfiguredRepoPathContract:
    def test_a_relative_local_resolves_against_the_workspace_root(self, tmp_path: Path) -> None:
        resolved = configured_repo_path({"local": "repos/engagement"}, tmp_path)

        assert resolved == (tmp_path / "repos" / "engagement").resolve()

    def test_an_absolute_local_is_taken_as_given(self, tmp_path: Path) -> None:
        absolute = tmp_path / "elsewhere"

        assert configured_repo_path({"local": str(absolute)}, tmp_path) == absolute.resolve()
