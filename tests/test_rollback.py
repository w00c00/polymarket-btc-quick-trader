import asyncio
from unittest import mock

import pytest

import poly_mm_pro_max as mod


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_trader():
    inst = mod.PolyQuickTrader.__new__(mod.PolyQuickTrader)
    inst.logger = mod.logging.getLogger("test_rollback")
    inst.log_live = lambda *a, **kw: None
    inst.clamp_price = mod.PolyQuickTrader.clamp_price.__get__(inst)
    inst.price_decimals = mod.PolyQuickTrader.price_decimals.__get__(inst)
    return inst


def test_flatten_uses_marketable_price_against_bid(monkeypatch):
    inst = _make_trader()
    calls = []

    async def fake_book(token_id):
        return {"bid": 0.40, "ask": 0.42, "tick_size": "0.01"}

    async def fake_sell(token_id, size, price, tick_size):
        calls.append({"token_id": token_id, "size": size, "price": price, "tick_size": tick_size})
        return {"success": True, "orderID": "0xabc"}

    async def fake_push(title, content):
        return None

    inst.best_bid_ask_for_token = fake_book
    inst.sell_token_limit = fake_sell
    inst.push_to_server_chan = fake_push

    positions = [{"layer": 1, "token_id": "tok-A", "tick_size": "0.01", "fill_size": 10.0, "entry": 0.5}]
    results = _run(inst._flatten_cycle_positions(positions, "test", cycle_count=3))
    assert len(results) == 1 and results[0]["ok"] is True
    assert calls[0]["price"] == 0.38  # 0.40 * 0.95 = 0.38


def test_flatten_floors_at_tick_when_bid_is_none(monkeypatch):
    inst = _make_trader()
    calls = []

    async def fake_book(token_id):
        return {"bid": None, "ask": None, "tick_size": "0.01"}

    async def fake_sell(token_id, size, price, tick_size):
        calls.append({"price": price})
        return {"success": True}

    async def fake_push(t, c):
        return None

    inst.best_bid_ask_for_token = fake_book
    inst.sell_token_limit = fake_sell
    inst.push_to_server_chan = fake_push

    positions = [{"layer": 1, "token_id": "tok-A", "tick_size": "0.01", "fill_size": 10.0, "entry": 0.5}]
    results = _run(inst._flatten_cycle_positions(positions, "test", cycle_count=3))
    assert results[0]["ok"] is True
    assert calls[0]["price"] == 0.01  # tick floor


def test_flatten_floors_at_tick_when_bid_times_0_95_below_tick(monkeypatch):
    """V8 patch: bid=0.005 (sub-tick) → 0.95*bid=0.00475 → must floor to tick=0.01."""
    inst = _make_trader()
    calls = []

    async def fake_book(token_id):
        return {"bid": 0.005, "ask": 0.10, "tick_size": "0.01"}

    async def fake_sell(token_id, size, price, tick_size):
        calls.append({"price": price})
        return {"success": True}

    async def fake_push(t, c):
        return None

    inst.best_bid_ask_for_token = fake_book
    inst.sell_token_limit = fake_sell
    inst.push_to_server_chan = fake_push

    positions = [{"layer": 1, "token_id": "tok-A", "tick_size": "0.01", "fill_size": 10.0, "entry": 0.5}]
    _run(inst._flatten_cycle_positions(positions, "test", cycle_count=3))
    assert calls[0]["price"] >= 0.01  # never clamps to 0


def test_flatten_continues_through_per_layer_errors(monkeypatch):
    inst = _make_trader()
    sell_call_count = {"n": 0}

    async def fake_book(token_id):
        return {"bid": 0.40, "ask": 0.42, "tick_size": "0.01"}

    async def fake_sell(token_id, size, price, tick_size):
        sell_call_count["n"] += 1
        if sell_call_count["n"] == 1:
            raise RuntimeError("simulated SDK error")
        return {"success": True}

    async def fake_push(t, c):
        return None

    inst.best_bid_ask_for_token = fake_book
    inst.sell_token_limit = fake_sell
    inst.push_to_server_chan = fake_push

    positions = [
        {"layer": 1, "token_id": "tok-A", "tick_size": "0.01", "fill_size": 10.0, "entry": 0.5},
        {"layer": 2, "token_id": "tok-B", "tick_size": "0.01", "fill_size": 8.0, "entry": 0.48},
    ]
    results = _run(inst._flatten_cycle_positions(positions, "test", cycle_count=3))
    assert len(results) == 2
    assert results[0]["ok"] is False
    assert results[1]["ok"] is True
    assert sell_call_count["n"] == 2


def test_flatten_pushes_server_chan_summary_once(monkeypatch):
    inst = _make_trader()
    push_calls = []

    async def fake_book(token_id):
        return {"bid": 0.40, "ask": 0.42, "tick_size": "0.01"}

    async def fake_sell(token_id, size, price, tick_size):
        return {"success": True}

    async def fake_push(title, content):
        push_calls.append({"title": title, "content": content})

    inst.best_bid_ask_for_token = fake_book
    inst.sell_token_limit = fake_sell
    inst.push_to_server_chan = fake_push

    positions = [
        {"layer": 1, "token_id": "tok-A", "tick_size": "0.01", "fill_size": 10.0, "entry": 0.5},
        {"layer": 2, "token_id": "tok-B", "tick_size": "0.01", "fill_size": 8.0, "entry": 0.48},
    ]
    _run(inst._flatten_cycle_positions(positions, "test_reason", cycle_count=7))
    assert len(push_calls) == 1
    assert "周期回滚" in push_calls[0]["title"]
    assert "test_reason" in push_calls[0]["content"]
    assert "layer 1" in push_calls[0]["content"]
    assert "layer 2" in push_calls[0]["content"]
