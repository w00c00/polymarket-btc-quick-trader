import asyncio
import time
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
    inst.logger = mod.logging.getLogger("test_retry_post")
    return inst


def test_post_succeeds_first_attempt_no_retry():
    inst = _make_trader()
    client = mock.MagicMock()
    client.post_order = mock.MagicMock(return_value={"success": True, "orderID": "0xabc", "status": "matched"})
    signed = object()  # opaque signed-order sentinel
    result = _run(inst._post_signed_order_with_retry(client, signed, per_attempt_timeout=10))
    assert result["orderID"] == "0xabc"
    assert client.post_order.call_count == 1
    # The signed_order sentinel must be passed identically
    assert client.post_order.call_args.args[0] is signed


def test_post_timeout_then_success_uses_same_signed_object():
    """Critical: retry must POST the exact same SignedOrderV2 instance so
    server-side dedup (by order hash) kicks in. Different instances would
    have different salts → different hashes → double order on retry."""
    inst = _make_trader()
    client = mock.MagicMock()
    call_log = []

    def post_order(signed, order_type, post_only):
        call_log.append(id(signed))
        if len(call_log) == 1:
            # Simulate the underlying SDK call hanging past wait_for's timeout
            time.sleep(0.3)
            return {"should_not_be_returned": True}
        return {"success": True, "orderID": "0xabc", "status": "matched"}

    client.post_order = post_order
    signed = object()
    result = _run(inst._post_signed_order_with_retry(client, signed, max_attempts=2, per_attempt_timeout=0.1))
    assert result["orderID"] == "0xabc"
    assert len(call_log) == 2
    assert call_log[0] == call_log[1]  # same id → same instance → safe dedup


def test_post_all_timeouts_raises_runtime():
    inst = _make_trader()
    client = mock.MagicMock()

    def post_order(signed, order_type, post_only):
        time.sleep(0.3)  # always hangs

    client.post_order = post_order
    signed = object()
    with pytest.raises(RuntimeError) as exc:
        _run(inst._post_signed_order_with_retry(client, signed, max_attempts=2, per_attempt_timeout=0.1))
    assert "重试" in str(exc.value) or "对账" in str(exc.value)


def test_post_non_timeout_exception_propagates_without_retry():
    """E.g. PolyApiException 401/400 should NOT trigger retry."""
    inst = _make_trader()
    client = mock.MagicMock()
    client.post_order = mock.MagicMock(side_effect=ValueError("not a timeout"))
    signed = object()
    with pytest.raises(ValueError):
        _run(inst._post_signed_order_with_retry(client, signed, max_attempts=2, per_attempt_timeout=10))
    # Only one call: non-timeout exceptions are not retried.
    assert client.post_order.call_count == 1


def test_post_passes_order_type_and_post_only_through():
    inst = _make_trader()
    client = mock.MagicMock()
    client.post_order = mock.MagicMock(return_value={"success": True, "orderID": "0xabc", "status": "matched"})
    signed = object()
    _run(inst._post_signed_order_with_retry(
        client, signed, order_type=mod.OrderType.FOK, post_only=True, per_attempt_timeout=5
    ))
    args, kwargs = client.post_order.call_args
    assert args[0] is signed
    assert args[1] == mod.OrderType.FOK
    assert args[2] is True
