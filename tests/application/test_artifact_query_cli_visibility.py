"""GAR visibility on the query-CLI search surface (single-root construction).

The CLI composition root injects the internal-type exclusion set into its
single-root repository, so `search` output must never contain GAR proxies while
`entities --type global-artifact-reference` (raw list access) keeps showing them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.cli.artifact_query_cli import main
from tests.support.search_visibility_fixtures import (
    GAR_ID,
    GAR_TYPE,
    QUERY,
    REQ_ID,
    build_engagement_repo,
)


class TestCliSearchHidesGar:
    def test_search_output_has_entity_but_no_gar(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        root = build_engagement_repo(tmp_path)
        exit_code = main(["search", QUERY, "--repo", str(root)])
        out = capsys.readouterr().out
        assert exit_code == 0
        assert REQ_ID in out
        assert GAR_ID not in out


class TestCliRawListKeepsGar:
    def test_entities_listing_by_type_still_shows_gar(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = build_engagement_repo(tmp_path)
        exit_code = main(["entities", "--repo", str(root), "--type", GAR_TYPE])
        out = capsys.readouterr().out
        assert exit_code == 0
        assert GAR_ID in out
