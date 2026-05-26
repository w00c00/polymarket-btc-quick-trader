from poly_mm_pro_max import PolyQuickTrader


def _extract(resp, limit_price=0.5, limit_size=10.0):
    return PolyQuickTrader._extract_fill(resp, limit_price=limit_price, limit_size=limit_size)


def test_extract_fill_matched_official_example():
    # Polymarket OpenAPI matched_order example, verbatim
    resp = {
        "success": True,
        "orderID": "0xabcdef1234567890abcdef1234567890abcdef12",
        "status": "matched",
        "makingAmount": "100000000",
        "takingAmount": "200000000",
        "transactionsHashes": ["0x1234567890abcdef1234567890abcdef12345678"],
        "tradeIDs": ["trade-123"],
        "errorMsg": "",
    }
    result = _extract(resp, limit_price=0.5, limit_size=200.0)
    assert result["verified"] is True
    assert result["status"] == "matched"
    assert result["fill_price"] == 0.5
    assert result["fill_size"] == 200.0  # 200000000 / 1e6


def test_extract_fill_live_status_falls_back_to_limit():
    # Polymarket OpenAPI live_order example: status="live" amounts are
    # order amounts, NOT fill amounts. Must NOT mark as verified.
    resp = {
        "success": True,
        "orderID": "0xabc...",
        "status": "live",
        "makingAmount": "100000000",
        "takingAmount": "200000000",
        "errorMsg": "",
    }
    result = _extract(resp, limit_price=0.55, limit_size=18.0)
    assert result["verified"] is False
    assert result["status"] == "live"
    assert result["fill_price"] == 0.55
    assert result["fill_size"] == 18.0


def test_extract_fill_delayed_status_falls_back_to_limit():
    resp = {
        "success": True,
        "status": "delayed",
        "makingAmount": "100000000",
        "takingAmount": "200000000",
        "errorMsg": "",
    }
    result = _extract(resp, limit_price=0.42, limit_size=24.0)
    assert result["verified"] is False
    assert result["status"] == "delayed"
    assert result["fill_price"] == 0.42
    assert result["fill_size"] == 24.0


def test_extract_fill_realistic_btc_market_fill():
    # 买 12 shares @ 0.4567 USDC 总价 5.4804 USDC
    # makingAmount = 5.4804 * 1e6 = 5480400
    # takingAmount = 12 * 1e6 = 12000000
    resp = {"status": "matched", "makingAmount": "5480400", "takingAmount": "12000000", "orderID": "0xabc"}
    result = _extract(resp, limit_price=0.46, limit_size=12.0)
    assert result["verified"] is True
    assert abs(result["fill_price"] - 0.4567) < 1e-9
    assert result["fill_size"] == 12.0


def test_extract_fill_price_improvement_against_limit():
    # 用户挂 0.55，实际成交 0.50 (better)
    resp = {"status": "matched", "makingAmount": "5000000", "takingAmount": "10000000"}
    result = _extract(resp, limit_price=0.55, limit_size=10.0)
    assert result["verified"] is True
    assert result["fill_price"] == 0.5
    assert result["fill_size"] == 10.0


def test_extract_fill_non_dict_response():
    result = _extract(None, limit_price=0.42, limit_size=7.0)
    assert result["verified"] is False
    assert result["status"] == "unverified"
    assert result["fill_price"] == 0.42
    assert result["fill_size"] == 7.0


def test_extract_fill_missing_amounts_with_matched_status():
    # 防御: status=matched 但缺 making/taking
    resp = {"status": "matched", "orderID": "0xabc"}
    result = _extract(resp, limit_price=0.5, limit_size=10.0)
    assert result["verified"] is False
    assert result["status"] == "matched"
    assert result["fill_size"] == 10.0


def test_extract_fill_invalid_amount_strings():
    resp = {"status": "matched", "makingAmount": "not-a-number", "takingAmount": "10000000"}
    result = _extract(resp, limit_price=0.5, limit_size=10.0)
    assert result["verified"] is False


def test_extract_fill_zero_taking_amount():
    resp = {"status": "matched", "makingAmount": "5000000", "takingAmount": "0"}
    result = _extract(resp, limit_price=0.5, limit_size=10.0)
    assert result["verified"] is False


def test_extract_fill_negative_making_amount():
    # schema drift / malformed: negative making
    resp = {"status": "matched", "makingAmount": "-5000000", "takingAmount": "10000000"}
    result = _extract(resp, limit_price=0.5, limit_size=10.0)
    assert result["verified"] is False


def test_extract_fill_price_out_of_range_above_one():
    # schema drift: making >> taking impossible for binary market
    resp = {"status": "matched", "makingAmount": "999000000", "takingAmount": "1000000"}
    result = _extract(resp, limit_price=0.5, limit_size=10.0)
    assert result["verified"] is False
    assert result["fill_size"] == 10.0  # falls back to limit_size


def test_extract_fill_price_at_one_boundary():
    # fill_price == 1.0 is impossible for a binary market in-progress
    resp = {"status": "matched", "makingAmount": "10000000", "takingAmount": "10000000"}
    result = _extract(resp, limit_price=0.5, limit_size=10.0)
    assert result["verified"] is False
