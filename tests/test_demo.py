import socket
from datetime import date

import pytest

from scripts.demo import run_demo
from tests.sample_fixture import build_sample

WEEK = date(2026, 11, 30)  # a Monday
TODAY = date(2026, 11, 29)


def test_demo_picks_one_class_per_slot(tmp_path):
    out = run_demo(build_sample(tmp_path), WEEK, TODAY)
    for slot in ("Mon", "Tue", "Wed"):
        assert slot in out
    assert "no_match" not in out


def test_demo_needs_no_network(tmp_path, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the demo tried to use the network")

    monkeypatch.setattr(socket, "socket", refuse)
    assert "Mon" in run_demo(build_sample(tmp_path), WEEK, TODAY)


def test_demo_on_a_low_energy_week(tmp_path):
    out = run_demo(build_sample(tmp_path, cycle_starts=[WEEK.isoformat()]), WEEK, TODAY)
    assert "no_match" not in out
    assert out.count("min") >= 3


def test_demo_says_it_ranks_from_saved_labels(tmp_path):
    assert "Ranked from Jev's saved labels" in run_demo(build_sample(tmp_path), WEEK, TODAY)


def test_low_energy_week_avoids_a_class_that_is_not_gentle(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    normal = run_demo(build_sample(tmp_path / "a"), WEEK, TODAY)
    gentle = run_demo(build_sample(tmp_path / "b", cycle_starts=[WEEK.isoformat()]), WEEK, TODAY)
    assert "Strength core 1" in normal
    assert "Strength core 1" not in gentle
