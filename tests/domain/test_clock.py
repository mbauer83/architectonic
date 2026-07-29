"""Tests for the central timezone-safe clock (src/domain/clock.py).

The guarantee under test: epochs and timestamps are UTC/POSIX regardless of the
host ``TZ``, so IDs and stored timestamps are identical across deployments.
"""

from __future__ import annotations

import os
import re
import time
from unittest import mock

from src.domain import clock


def test_epoch_seconds_is_int_posix() -> None:
    before = int(time.time())
    value = clock.epoch_seconds()
    after = int(time.time())
    assert isinstance(value, int)
    assert before <= value <= after


def test_utc_now_iso_format_has_trailing_z() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", clock.utc_now_iso())


def test_utc_now_compact_is_filename_safe() -> None:
    stamp = clock.utc_now_compact()
    assert re.fullmatch(r"\d{8}T\d{6}Z", stamp)
    assert "/" not in stamp and ":" not in stamp


def test_epoch_independent_of_local_timezone() -> None:
    # POSIX epoch seconds are an absolute instant; changing TZ must not shift it.
    fixed = 1_700_000_000.0
    with mock.patch.object(time, "time", return_value=fixed):
        with mock.patch.dict(os.environ, {"TZ": "America/Los_Angeles"}):
            if hasattr(time, "tzset"):
                time.tzset()
            west = clock.epoch_seconds()
        with mock.patch.dict(os.environ, {"TZ": "Asia/Tokyo"}):
            if hasattr(time, "tzset"):
                time.tzset()
            east = clock.epoch_seconds()
    if hasattr(time, "tzset"):
        time.tzset()  # restore the process default for subsequent tests
    assert west == east == int(fixed)


def test_frozen_now_pins_every_reader_to_one_instant() -> None:
    with clock.frozen_now("2026-07-24T09:15:00Z"):
        assert clock.utc_now_iso() == "2026-07-24T09:15:00Z"
        assert clock.utc_now_compact() == "20260724T091500Z"
        assert clock.epoch_seconds() == int(clock.epoch_from_iso("2026-07-24T09:15:00Z"))


def test_frozen_now_restores_the_real_clock_afterwards() -> None:
    with clock.frozen_now("2020-01-01T00:00:00Z"):
        pass
    assert clock.utc_now_iso() != "2020-01-01T00:00:00Z"
    assert abs(clock.epoch_seconds() - int(time.time())) <= 1


def test_frozen_now_accepts_posix_seconds_and_nests() -> None:
    with clock.frozen_now(1_700_000_000.0):
        assert clock.utc_now_iso() == "2023-11-14T22:13:20Z"
        with clock.frozen_now("2026-01-02T03:04:05Z"):
            assert clock.utc_now_iso() == "2026-01-02T03:04:05Z"
        assert clock.utc_now_iso() == "2023-11-14T22:13:20Z"


def test_iso_is_utc_not_local() -> None:
    # utc_now_iso formats from time.gmtime() (UTC). Patch gmtime to a fixed UTC
    # struct and confirm the rendered string is that UTC instant, unchanged by TZ.
    fixed_utc = time.struct_time((2023, 11, 14, 22, 13, 20, 1, 318, 0))
    with mock.patch.object(time, "gmtime", return_value=fixed_utc):
        with mock.patch.dict(os.environ, {"TZ": "America/Los_Angeles"}):
            if hasattr(time, "tzset"):
                time.tzset()
            west = clock.utc_now_iso()
        with mock.patch.dict(os.environ, {"TZ": "Asia/Tokyo"}):
            if hasattr(time, "tzset"):
                time.tzset()
            east = clock.utc_now_iso()
    if hasattr(time, "tzset"):
        time.tzset()  # restore the process default for subsequent tests
    assert west == east == "2023-11-14T22:13:20Z"
