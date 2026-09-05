"""Tests for the offline-safe parts of scripts/collect.py.

collect.py talks to the GitHub and SonarCloud APIs, so only its pure helpers
are exercised here. Nothing in this file performs, or may perform, network I/O
-- ``test_import_is_offline`` enforces that for the import itself.
"""
from datetime import datetime, timedelta, timezone

import pytest

from scripts import collect


def test_ts_parses_github_zulu_timestamps():
    got = collect._ts("2026-08-30T15:33:30Z")
    assert got == datetime(2026, 8, 30, 15, 33, 30, tzinfo=timezone.utc)
    assert got.tzinfo is not None, "must be timezone-aware or later arithmetic breaks"


def test_ts_parses_explicit_offsets():
    got = collect._ts("2026-08-30T11:33:30-04:00")
    assert got == datetime(2026, 8, 30, 15, 33, 30, tzinfo=timezone.utc)
    assert got.utcoffset() == timedelta(hours=-4)


def test_ts_keeps_fractional_seconds():
    assert collect._ts("2026-08-30T15:33:30.672711Z").microsecond == 672711


@pytest.mark.parametrize("empty", [None, ""])
def test_ts_returns_none_for_missing_values(empty):
    """The API returns null for e.g. merged_at on an open PR."""
    assert collect._ts(empty) is None


def test_ts_rejects_garbage():
    with pytest.raises(ValueError):
        collect._ts("last Tuesday")


def test_ts_values_are_comparable_across_zones():
    assert collect._ts("2026-08-30T15:33:30Z") == collect._ts("2026-08-30T11:33:30-04:00")


def test_window_constants_are_coherent():
    assert collect.WINDOW_DAYS > 0
    assert collect.SINCE < collect.NOW
    assert (collect.NOW - collect.SINCE).days == collect.WINDOW_DAYS
    assert collect.EPOCH == datetime(2020, 1, 1, tzinfo=timezone.utc)


def test_epoch_hours_conversion_matches_the_renderer_contract():
    """The page converts an hour back with Date.UTC(2020,0,1)+h*3600e3, so the
    collector's hour numbers have to be whole hours since that epoch."""
    h = int((collect._ts("2026-08-30T15:33:30Z") - collect.EPOCH).total_seconds() // 3600)
    assert collect.EPOCH + timedelta(hours=h) == datetime(2026, 8, 30, 15, tzinfo=timezone.utc)


def test_api_target_is_github():
    assert collect.API == "https://api.github.com"


def test_import_is_offline(monkeypatch):
    """Importing the collector must not open a socket."""
    import importlib
    import socket

    def boom(*a, **k):
        raise AssertionError("collect.py opened a socket at import time")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr("urllib.request.urlopen", boom)
    importlib.reload(collect)
