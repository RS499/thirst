"""Timeline strip: run labels (pure Python) and block geometry (real browser).

    python3 -m pytest tests/test_timeline.py

The geometry test drives the served page in Chrome and needs the API running
(python3 -m uvicorn api:app --port 8600, or GRIDSHIFT_URL); it is skipped otherwise.
It makes no model call: /place is pure Python, and the timeline under test is set
directly on the record the page renders.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api import PlaceIn, _timeline  # noqa: E402

SAT = 5
URL = os.environ.get("GRIDSHIFT_URL", "http://localhost:8600")


def labels(arrival_clock: int, shift: int, duration: int, window: int, dow: int = SAT) -> tuple[str, str]:
    body = PlaceIn(arrival_hour=arrival_clock + 1, window_h=window, season="SON",
                   duration_h=duration, now_dow=dow)
    _, d = _timeline(SimpleNamespace(shift_h=shift), body)
    return d["timeline.start"], d["timeline.end"]


def test_run_crossing_midnight_names_both_days():
    assert labels(19, 1, 20, 60) == ("8 PM Sat", "4 PM Sun")


def test_run_within_arrival_day_names_no_day():
    assert labels(19, 1, 2, 12) == ("8 PM", "10 PM")


def test_run_within_later_day_names_it_once_on_the_end():
    assert labels(19, 8, 2, 12) == ("3 AM", "5 AM Sun")


# ------------------------------------------------------------------ browser geometry

CASES = [  # (name, shift) for a 20 h job in a 60 h window: block width is always 1/3
    ("very start", 0),
    ("middle", 20),
    ("latest possible start", 60 - 20),
]


@pytest.fixture(scope="module")
def page():
    httpx = pytest.importorskip("httpx")
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        httpx.get(URL, timeout=2).raise_for_status()
    except Exception:
        pytest.skip(f"GridShift API not reachable at {URL}")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        pg = browser.new_page(viewport={"width": 1440, "height": 1000})
        pg.goto(URL, wait_until="networkidle")
        yield pg
        browser.close()


@pytest.mark.parametrize("name,shift", CASES)
def test_block_left_and_width_are_fractions_of_the_full_window(page, name, shift):
    window, duration = 60, 20
    frac = page.evaluate("""async ([shift, duration, window]) => {
        const req = {arrival_hour: 20, window_h: window, season: "SON", duration_h: duration, now_dow: 5};
        const placed = await api("/place", req);
        const rec = placed.records[basis()][objective()];
        rec.timeline = {shift, duration, window};
        Object.assign(state, {req, placed, cls: {window_h: window, display: {window_h: `${window} h`}}});
        render(true);
        await new Promise(r => setTimeout(r, 400));            // past the 250 ms transition
        const tr = document.querySelector("#v-tl .tl-track").getBoundingClientRect();
        const j = document.getElementById("v-tl-job").getBoundingClientRect();
        const border = 1;                                       // the track's 1 px border
        const inner = tr.width - 2 * border;
        return {left: (j.left - tr.left - border) / inner, width: j.width / inner};
    }""", [shift, duration, window])
    assert frac["left"] == pytest.approx(shift / window, abs=0.005), name
    assert frac["width"] == pytest.approx(duration / window, abs=0.005), name


# ------------------------------------------------------------------ split placement

from itertools import product  # noqa: E402

from gridshift.place import OBJECTIVES, _season_profile, place, place_split  # noqa: E402
from gridshift.signals import METRICS  # noqa: E402

JOBS = list(product(("SON", "DJF"), (20, 9), (12, 24, 40), (3, 6), ("average", "marginal_empirical")))


def hours_at(arrival: int, window: int) -> dict[int, int]:
    """Offset from arrival -> hour-ending number, for every hour in the window."""
    return {off: (arrival - 1 + off) % 24 + 1 for off in range(window)}


@pytest.mark.parametrize("season,arrival,window,duration,basis", JOBS)
def test_split_picks_exactly_the_n_cheapest_hours(season, arrival, window, duration, basis):
    prof, at = _season_profile(season, basis), hours_at(arrival, window)
    for objective, metric in OBJECTIVES.items():
        col = METRICS[metric]
        want = tuple(sorted(sorted(at, key=lambda o: (prof.at[at[o], col], o))[:duration]))
        assert place_split(arrival, window, season, duration, basis=basis)[objective].hours == want


@pytest.mark.parametrize("season,arrival,window,duration,basis", JOBS)
def test_split_is_never_worse_than_any_contiguous_block(season, arrival, window, duration, basis):
    """Priced the same way (mean over the hours run), the cheapest hours beat every block."""
    prof, at = _season_profile(season, basis), hours_at(arrival, window)
    for objective, metric in OBJECTIVES.items():
        col = METRICS[metric]
        mean = lambda hs: sum(float(prof.at[h, col]) for h in hs) / len(hs)  # noqa: E731
        best_block = min(mean([at[start + k] for k in range(duration)])
                         for start in range(window - duration + 1))
        rec = place_split(arrival, window, season, duration, basis=basis)[objective]
        assert mean([at[o] for o in rec.hours]) <= best_block + 1e-9


@pytest.mark.parametrize("season,arrival,window,_d,basis", JOBS)
def test_one_hour_job_is_identical_in_both_modes(season, arrival, window, _d, basis):
    contiguous = place(arrival, window, season, basis=basis)
    split = place_split(arrival, window, season, 1, basis=basis)
    for objective in OBJECTIVES:
        a, b = contiguous[objective], split[objective]
        assert (a.placed, a.shift_h) == (b.placed, b.shift_h)
        assert [a.carbon, a.withdrawal, a.consumption] == [b.carbon, b.withdrawal, b.consumption]
        assert a.display == {k: v for k, v in b.display.items() if k != "hours_n"}
