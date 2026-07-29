"""Tests for parsing/serializing a ``ViewpointApplication`` from/to the ``viewpoint: {...}``
frontmatter mapping a diagram or matrix file carries."""

from __future__ import annotations

import pytest

from src.domain.viewpoints.viewpoint_application_parsing import (
    parse_viewpoint_application,
    viewpoint_application_to_mapping,
)


class TestParseViewpointApplication:
    def test_absent_value_is_none(self) -> None:
        assert parse_viewpoint_application(None, target_kind="diagram", target_id="DGM@1.x.a") is None

    def test_parses_minimal_mapping(self) -> None:
        application = parse_viewpoint_application(
            {"slug": "motivation", "version": 2}, target_kind="diagram", target_id="DGM@1.x.a"
        )
        assert application is not None
        assert application.target_kind == "diagram"
        assert application.target_id == "DGM@1.x.a"
        assert application.viewpoint_slug == "motivation"
        assert application.pinned_version == 2
        assert application.enforcement_override is None
        assert application.derivation_params == {}

    def test_parses_enforcement_override_and_derivation_params(self) -> None:
        application = parse_viewpoint_application(
            {"slug": "motivation", "version": 1, "enforcement_override": "off", "derivation_params": {"depth": 2}},
            target_kind="matrix",
            target_id="MTX@1.x.a",
        )
        assert application is not None
        assert application.enforcement_override == "off"
        assert application.derivation_params == {"depth": 2}

    def test_non_mapping_value_rejected_loudly(self) -> None:
        with pytest.raises(ValueError, match="mapping"):
            parse_viewpoint_application("not-a-mapping", target_kind="diagram", target_id="DGM@1.x.a")

    def test_missing_slug_rejected_loudly(self) -> None:
        with pytest.raises(ValueError, match="slug"):
            parse_viewpoint_application({"version": 1}, target_kind="diagram", target_id="DGM@1.x.a")

    def test_invalid_enforcement_override_rejected_loudly(self) -> None:
        with pytest.raises(ValueError, match="enforcement_override"):
            parse_viewpoint_application(
                {"slug": "motivation", "version": 1, "enforcement_override": "sometimes"},
                target_kind="diagram",
                target_id="DGM@1.x.a",
            )


class TestViewpointApplicationToMapping:
    def test_round_trips_minimal(self) -> None:
        application = parse_viewpoint_application(
            {"slug": "motivation", "version": 2}, target_kind="diagram", target_id="DGM@1.x.a"
        )
        assert application is not None
        mapping = viewpoint_application_to_mapping(application)
        assert mapping == {"slug": "motivation", "version": 2}
        reparsed = parse_viewpoint_application(mapping, target_kind="diagram", target_id="DGM@1.x.a")
        assert reparsed == application

    def test_round_trips_with_enforcement_override_and_params(self) -> None:
        application = parse_viewpoint_application(
            {"slug": "motivation", "version": 1, "enforcement_override": "ghost", "derivation_params": {"depth": 3}},
            target_kind="matrix",
            target_id="MTX@1.x.a",
        )
        assert application is not None
        mapping = viewpoint_application_to_mapping(application)
        assert mapping["enforcement_override"] == "ghost"
        assert mapping["derivation_params"] == {"depth": 3}
        reparsed = parse_viewpoint_application(mapping, target_kind="matrix", target_id="MTX@1.x.a")
        assert reparsed == application
