import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core import (  # noqa: E402
    REVERSAL_MODE_GREEN_DOWN,
    REVERSAL_MODE_RED_UP,
    reversal_profile,
    reversal_stakes,
    run_reversal_backtest_from_rows,
)


def fake_row(ts, open_price, close_price):
    return [ts, str(open_price), str(max(open_price, close_price)), str(min(open_price, close_price)), str(close_price), "0", ts + 900000 - 1]


def test_sizing_default():
    sizing = reversal_stakes(5, 0.5, 3, 0.07)
    rounded = [round(x, 2) for x in sizing["stakes"]]
    assert rounded == [5.0, 10.36, 21.48]
    assert round(sizing["worst_loss"], 2) == 38.13


def test_profiles_are_opposites():
    assert reversal_profile(REVERSAL_MODE_RED_UP)["direction"] == "UP"
    assert reversal_profile(REVERSAL_MODE_GREEN_DOWN)["direction"] == "DOWN"


def test_red_up_backtest_wins_after_three_red():
    rows = [
        fake_row(0, 10, 11),
        fake_row(900000, 11, 10),
        fake_row(1800000, 10, 9),
        fake_row(2700000, 9, 8),
        fake_row(3600000, 8, 9),
        fake_row(4500000, 9, 10),
    ]
    rows.extend(fake_row((index + 6) * 900000, 10 + index, 11 + index) for index in range(6))
    result = run_reversal_backtest_from_rows(rows, REVERSAL_MODE_RED_UP, 5, 3, 0.5)
    assert result["cycles"] == 1
    assert result["wins"] == 1


def test_green_down_backtest_wins_after_three_green():
    rows = [
        fake_row(0, 10, 9),
        fake_row(900000, 9, 10),
        fake_row(1800000, 10, 11),
        fake_row(2700000, 11, 12),
        fake_row(3600000, 12, 11),
        fake_row(4500000, 11, 10),
    ]
    rows.extend(fake_row((index + 6) * 900000, 10 - index, 9 - index) for index in range(6))
    result = run_reversal_backtest_from_rows(rows, REVERSAL_MODE_GREEN_DOWN, 5, 3, 0.5)
    assert result["cycles"] == 1
    assert result["wins"] == 1
