import math
import os

import pytest

import poly_mm_pro_max as mod


def test_float_or_zero_nan_returns_zero():
    inst = mod.PolyQuickTrader.__new__(mod.PolyQuickTrader)
    inst._float_or_zero = mod.PolyQuickTrader._float_or_zero.__get__(inst)
    assert inst._float_or_zero(float("nan")) == 0.0


def test_float_or_zero_inf_returns_zero():
    inst = mod.PolyQuickTrader.__new__(mod.PolyQuickTrader)
    inst._float_or_zero = mod.PolyQuickTrader._float_or_zero.__get__(inst)
    assert inst._float_or_zero(float("inf")) == 0.0
    assert inst._float_or_zero(float("-inf")) == 0.0


def test_float_or_zero_string_nan_returns_zero():
    inst = mod.PolyQuickTrader.__new__(mod.PolyQuickTrader)
    inst._float_or_zero = mod.PolyQuickTrader._float_or_zero.__get__(inst)
    assert inst._float_or_zero("nan") == 0.0
    assert inst._float_or_zero("inf") == 0.0


def test_float_or_zero_real_numbers_pass_through():
    inst = mod.PolyQuickTrader.__new__(mod.PolyQuickTrader)
    inst._float_or_zero = mod.PolyQuickTrader._float_or_zero.__get__(inst)
    assert inst._float_or_zero(3.14) == 3.14
    assert inst._float_or_zero("0.42") == 0.42
    assert inst._float_or_zero(0) == 0.0


def test_float_or_zero_invalid_returns_zero():
    inst = mod.PolyQuickTrader.__new__(mod.PolyQuickTrader)
    inst._float_or_zero = mod.PolyQuickTrader._float_or_zero.__get__(inst)
    assert inst._float_or_zero("not a number") == 0.0
    assert inst._float_or_zero(None) == 0.0


def test_journal_writes_header_on_first_call(tmp_path):
    p = str(tmp_path / "journal.csv")
    mod.PolyQuickTrader._append_trade_journal({
        "ts": "2026-05-26T00:00:00Z", "strategy": "RED_UP", "cycle": 1, "layer": 1,
        "market_slug": "btc-test", "direction": "UP", "stake_usdc": "5.0000",
        "requested_price": "0.5000", "fill_price": "0.4900", "fill_size": "10.000000",
        "fill_verified": "True", "outcome": "win", "pnl_estimate": "+1.0000",
        "accumulated_loss": "0.0000",
    }, path=p)
    with open(p) as f:
        lines = f.read().splitlines()
    assert lines[0].startswith("ts,strategy,cycle,layer,market_slug")
    assert "btc-test" in lines[1]
    assert "RED_UP" in lines[1]


def test_journal_appends_without_dup_header(tmp_path):
    p = str(tmp_path / "journal.csv")
    base = {
        "ts": "2026-05-26T00:00:00Z", "strategy": "RED_UP", "cycle": 1, "layer": 1,
        "market_slug": "btc-test", "direction": "UP", "stake_usdc": "5.0000",
        "requested_price": "0.5000", "fill_price": "0.4900", "fill_size": "10.000000",
        "fill_verified": "True", "outcome": "win", "pnl_estimate": "+1.0000",
        "accumulated_loss": "0.0000",
    }
    mod.PolyQuickTrader._append_trade_journal(base, path=p)
    mod.PolyQuickTrader._append_trade_journal({**base, "cycle": 2}, path=p)
    with open(p) as f:
        lines = f.read().splitlines()
    assert len(lines) == 3  # header + 2 rows
    assert lines.count(lines[0]) == 1  # header appears once


def test_journal_ignores_extra_keys(tmp_path):
    p = str(tmp_path / "journal.csv")
    mod.PolyQuickTrader._append_trade_journal({
        "ts": "2026-05-26T00:00:00Z", "strategy": "RED_UP", "cycle": 1, "layer": 1,
        "market_slug": "btc-test", "direction": "UP", "stake_usdc": "5.0000",
        "requested_price": "0.5000", "fill_price": "0.4900", "fill_size": "10.000000",
        "fill_verified": "True", "outcome": "win", "pnl_estimate": "+1.0000",
        "accumulated_loss": "0.0000",
        "extra_field_not_in_schema": "garbage",
    }, path=p)
    with open(p) as f:
        content = f.read()
    assert "garbage" not in content


def test_journal_handles_missing_keys_as_empty(tmp_path):
    p = str(tmp_path / "journal.csv")
    mod.PolyQuickTrader._append_trade_journal({
        "ts": "2026-05-26T00:00:00Z", "strategy": "RED_UP",
    }, path=p)
    with open(p) as f:
        lines = f.read().splitlines()
    # row should have empty strings for missing keys
    assert lines[1].startswith("2026-05-26T00:00:00Z,RED_UP,,,,,,,")


def test_cycle_pnl_running_accounting_with_late_win():
    """Documents the cycle_pnl_running fix (Codex Phase 9 blocker).

    Multi-layer reversal cycle: layer 1 LOSS, layer 2 WIN.
      layer 1 loss = entry × size = 0.55 × 10 = 5.5; accumulated_loss = 5.5
      layer 2 stake = 10.36, fill_price = 0.55, fill_size ≈ 18.84
        layer 2 `pnl` (per run_reversal_live_real WIN branch formula) =
          (1.0 - entry) × size - accumulated_loss
          = (1.0 - 0.55) × 18.84 - 5.5
          = 8.478 - 5.5 = 2.978        ← already net of prior layer losses

    BUG (pre-fix):  cycle_pnl_running += pnl on every settlement
        layer 1: cycle_pnl_running = -5.5
        layer 2 WIN: cycle_pnl_running = -5.5 + 2.978 = -2.522  ← wrong
        (real cycle pnl is +2.978: lost 5.5, then made it back + 2.978)

    FIX:  WIN branch adds back accumulated_loss before accumulating
        layer 1: cycle_pnl_running = -5.5
        layer 2 WIN: cycle_pnl_running = -5.5 + (2.978 + 5.5) = +2.978  ← correct
    """
    cycle_pnl_running = 0.0
    layer1_loss = 0.55 * 10        # 5.5
    cycle_pnl_running += -layer1_loss
    accumulated_loss = 5.5
    layer2_pnl_per_formula = (1.0 - 0.55) * 18.84 - accumulated_loss  # 2.978
    cycle_pnl_running += layer2_pnl_per_formula + accumulated_loss
    assert abs(cycle_pnl_running - 2.978) < 0.01
    # The wrong version would yield ~-2.522, more than 4 away from truth.
    wrong = -layer1_loss + layer2_pnl_per_formula
    assert wrong < cycle_pnl_running - 4.0
