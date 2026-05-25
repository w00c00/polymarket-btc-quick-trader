import asyncio
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

import aiohttp


GAMMA_EVENT_SLUG_URL = "https://gamma-api.polymarket.com/events/slug"
POLYMARKET_BASE_URL = "https://polymarket.com"
BEIJING_TZ = timezone(timedelta(hours=8))

REVERSAL_MODE_RED_UP = "三连阴转UP"
REVERSAL_MODE_GREEN_DOWN = "三连阳转DOWN"


@dataclass
class QuickMarket:
    slug: str
    event_slug: str
    question: str
    yes_id: str
    no_id: str
    tick_size: str
    period: str
    start_dt: str | None
    end_dt: str | None
    start_dt_bj: str | None
    end_dt_bj: str | None
    time_label_bj: str
    ended: bool
    up_bid: float
    up_ask: float
    down_bid: float
    down_ask: float
    spread: float
    volume24h: float


def optional_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def float_or_zero(value):
    parsed = optional_float(value)
    return 0.0 if parsed is None else parsed


def parse_datetime(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def fmt_beijing(dt: datetime | None, with_tz=True):
    if not dt:
        return None
    value = dt.astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M")
    return f"{value} 北京时间" if with_tz else value


def slug_start_datetime(slug: str):
    match = re.search(r"updown-\d+[mh]-(\d{9,})", slug)
    if not match:
        return None
    return datetime.fromtimestamp(int(match.group(1)), tz=timezone.utc)


def period_seconds(period: str):
    match = re.fullmatch(r"(\d+)([mh])", period or "")
    if not match:
        return None
    value = int(match.group(1))
    return value * (60 if match.group(2) == "m" else 3600)


def parse_token_ids(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except Exception:
        pass
    return [part.strip().strip('"') for part in str(value).strip("[]").split(",") if part.strip()]


def quick_period_from_slug_or_title(slug: str, question: str):
    match = re.search(r"updown-(\d+[mh])-", slug)
    if match:
        return match.group(1)
    lower = question.lower()
    if "15" in lower and ("minute" in lower or "min" in lower):
        return "15m"
    if "5" in lower and ("minute" in lower or "min" in lower):
        return "5m"
    if "hour" in lower or re.search(r"\d+(am|pm)", lower):
        return "1h"
    if re.search(r"\bon\s+[a-z]+-\d{1,2}-\d{4}\b", slug) or " on " in lower:
        return "1d"
    return "?"


def generated_btc_updown_slugs():
    now_ts = int(time.time())
    slugs = []
    for period, seconds in (("5m", 300), ("15m", 900), ("4h", 14400)):
        base = now_ts - (now_ts % seconds)
        for offset in (-2, -1, 0, 1, 2):
            start_ts = base + offset * seconds
            if start_ts > 0:
                slugs.append(f"btc-updown-{period}-{start_ts}")
    return slugs


def quick_market_candidate(event: dict, market: dict, now: datetime):
    if market.get("closed") is True or market.get("active") is False or market.get("acceptingOrders") is False:
        return None
    token_ids = parse_token_ids(market.get("clobTokenIds"))
    if len(token_ids) < 2:
        return None
    question = market.get("question") or event.get("title") or ""
    slug = market.get("slug") or event.get("slug") or ""
    if "bitcoin" not in question.lower() and "btc" not in slug.lower():
        return None
    if "up" not in question.lower() or "down" not in question.lower():
        return None

    period = quick_period_from_slug_or_title(slug, question)
    start_dt = slug_start_datetime(slug)
    seconds = period_seconds(period)
    slug_end_dt = start_dt + timedelta(seconds=seconds) if start_dt and seconds else None
    end_dt = slug_end_dt or parse_datetime(market.get("endDate") or event.get("endDate"))
    best_bid = optional_float(market.get("bestBid"))
    best_ask = optional_float(market.get("bestAsk"))
    if best_bid is None or best_ask is None or best_bid <= 0 or best_ask >= 1 or best_bid >= best_ask:
        return None

    return QuickMarket(
        slug=slug,
        event_slug=event.get("slug") or slug,
        question=question,
        yes_id=token_ids[0],
        no_id=token_ids[1],
        tick_size=str(market.get("orderPriceMinTickSize") or "0.01"),
        period=period,
        start_dt=start_dt.isoformat() if start_dt else None,
        end_dt=end_dt.isoformat() if end_dt else None,
        start_dt_bj=fmt_beijing(start_dt, with_tz=False),
        end_dt_bj=fmt_beijing(end_dt, with_tz=False),
        time_label_bj=(
            f"{fmt_beijing(start_dt, with_tz=False)} - {fmt_beijing(end_dt, with_tz=False)} 北京时间"
            if start_dt and end_dt else (fmt_beijing(end_dt) or "--")
        ),
        ended=bool(end_dt and end_dt <= now),
        up_bid=best_bid,
        up_ask=best_ask,
        down_bid=max(0.0, 1.0 - best_ask),
        down_ask=min(1.0, 1.0 - best_bid),
        spread=best_ask - best_bid,
        volume24h=float_or_zero(market.get("volume24hrClob") or market.get("volume24hr")),
    )


class MarketData:
    def __init__(self):
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self._cache = {}

    def clear_cache(self):
        self._cache.clear()

    async def fetch_json(self, url: str, params=None):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), headers=self.headers) as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    raise RuntimeError(f"GET {url} HTTP {response.status}")
                return await response.json()

    async def fetch_text(self, url: str):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), headers=self.headers) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise RuntimeError(f"GET {url} HTTP {response.status}")
                return await response.text()

    async def fetch_quick_btc_markets(self):
        cache_key = "quick_markets"
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached["ts"] < 20:
            return cached["value"]
        html = await self.fetch_text(f"{POLYMARKET_BASE_URL}/crypto/bitcoin")
        slugs = []
        for match in re.finditer(r'href="/(?:zh/)?event/([^"?#/]+)', html):
            slug = match.group(1)
            if slug.endswith("/live"):
                slug = slug.rsplit("/", 1)[0]
            if slug in slugs:
                continue
            if slug.startswith("btc-updown-") or slug.startswith("bitcoin-up-or-down-"):
                slugs.append(slug)
        for slug in generated_btc_updown_slugs():
            if slug not in slugs:
                slugs.insert(0, slug)

        now = datetime.now(timezone.utc)
        markets = []
        for slug in slugs[:80]:
            try:
                event = await self.fetch_json(f"{GAMMA_EVENT_SLUG_URL}/{slug}")
            except Exception:
                continue
            if not isinstance(event, dict):
                continue
            for market in event.get("markets") or []:
                item = quick_market_candidate(event, market, now)
                if item:
                    markets.append(asdict(item))
        markets.sort(key=lambda item: (item["ended"], item["end_dt"] or "9999"))
        value = markets[:20]
        self._cache[cache_key] = {"ts": time.time(), "value": value}
        return value

    async def fetch_btc_15m_klines(self, days=7, limit=1000):
        cache_key = f"klines:{days}:{limit}"
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached["ts"] < 60:
            return cached["value"]
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - int(days * 24 * 3600 * 1000)
        rows = []
        current = start_ms
        urls = ["https://api.binance.com/api/v3/klines", "https://data-api.binance.vision/api/v3/klines"]
        while current < end_ms:
            params = {
                "symbol": "BTCUSDT",
                "interval": "15m",
                "startTime": str(current),
                "endTime": str(end_ms),
                "limit": str(limit),
            }
            data = None
            last_error = None
            for url in urls:
                try:
                    data = await self.fetch_json(url, params=params)
                    break
                except Exception as exc:
                    last_error = exc
            if data is None:
                raise RuntimeError(f"读取 Binance 15m K 线失败: {last_error}")
            if not data:
                break
            rows.extend(data)
            next_start = int(data[-1][0]) + 15 * 60 * 1000
            if next_start <= current:
                break
            current = next_start
            await asyncio.sleep(0.02)

        now_ms = int(time.time() * 1000)
        deduped = {}
        for row in rows:
            if int(row[6]) <= now_ms:
                deduped[int(row[0])] = row
        value = [deduped[key] for key in sorted(deduped)]
        self._cache[cache_key] = {"ts": time.time(), "value": value}
        return value


def reversal_profile(mode):
    if mode == REVERSAL_MODE_GREEN_DOWN:
        return {
            "mode": REVERSAL_MODE_GREEN_DOWN,
            "label": "三连阳转阴 DOWN",
            "trigger_color": "G",
            "trigger_name": "阳线",
            "win_color": "R",
            "direction": "DOWN",
        }
    return {
        "mode": REVERSAL_MODE_RED_UP,
        "label": "三连阴转阳 UP",
        "trigger_color": "R",
        "trigger_name": "阴线",
        "win_color": "G",
        "direction": "UP",
    }


def reversal_factors(entry_price: float, fee_rate: float = 0.07):
    win_factor = 1.0 / entry_price - 1.0 - fee_rate * (1.0 - entry_price)
    loss_factor = 1.0 + fee_rate * (1.0 - entry_price)
    return win_factor, loss_factor


def reversal_stakes(initial_usdc: float, entry_price: float, max_layers: int, fee_rate: float = 0.07):
    win_factor, loss_factor = reversal_factors(entry_price, fee_rate)
    target_profit = win_factor * initial_usdc
    stakes = []
    accumulated_loss = 0.0
    for _ in range(max_layers):
        stake = (accumulated_loss + target_profit) / win_factor
        stakes.append(stake)
        accumulated_loss += loss_factor * stake
    return {
        "stakes": stakes,
        "stake_sum": sum(stakes),
        "win_factor": win_factor,
        "loss_factor": loss_factor,
        "target_profit": target_profit,
        "worst_loss": accumulated_loss,
        "recommended_single_strategy_usdc": round(accumulated_loss * 1.25, 2),
        "recommended_both_strategies_usdc": round(accumulated_loss * 2.5, 2),
    }


def kline_color(row):
    open_price = float(row[1])
    close_price = float(row[4])
    if close_price < open_price:
        return "R"
    if close_price > open_price:
        return "G"
    return "D"


def rsi_from_closes(closes, period=14):
    if len(closes) <= period:
        return 50.0
    gains = []
    losses = []
    for prev, curr in zip(closes[-period - 1:-1], closes[-period:]):
        change = curr - prev
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def local_btc_probability_from_rows(rows, market=None):
    if len(rows) < 40:
        raise ValueError("K 线数量不足，无法预测。")
    closes = [float(row[4]) for row in rows]
    colors = [kline_color(row) for row in rows]
    last = closes[-1]

    ret_3 = closes[-1] / closes[-4] - 1.0
    ret_8 = closes[-1] / closes[-9] - 1.0
    ret_16 = closes[-1] / closes[-17] - 1.0
    rsi = rsi_from_closes(closes)
    recent_red = colors[-3:] == ["R", "R", "R"]
    recent_green = colors[-3:] == ["G", "G", "G"]

    score = 0.0
    score += max(min(ret_3 * 1800.0, 0.16), -0.16)
    score += max(min(ret_8 * 950.0, 0.16), -0.16)
    score += max(min(ret_16 * 520.0, 0.14), -0.14)
    score += max(min((rsi - 50.0) / 260.0, 0.11), -0.11)

    reversal_hint = "无明显三连反转"
    if recent_red:
        score += 0.07
        reversal_hint = "三连阴后偏反弹"
    elif recent_green:
        score -= 0.07
        reversal_hint = "三连阳后偏回落"

    up_probability = min(0.82, max(0.18, 0.5 + score))
    down_probability = 1.0 - up_probability
    confidence = min(0.86, max(0.28, abs(up_probability - 0.5) * 1.6 + 0.32))

    if up_probability >= 0.56:
        action = "BUY_UP"
    elif down_probability >= 0.56:
        action = "BUY_DOWN"
    else:
        action = "WAIT"

    return {
        "market": market or {},
        "last_price": last,
        "last_kline": fmt_kline_time(rows[-1]),
        "last_kline_bj": fmt_kline_time(rows[-1]),
        "up_probability": up_probability,
        "down_probability": down_probability,
        "confidence": confidence,
        "action": action,
        "signals": {
            "ret_45m": ret_3,
            "ret_120m": ret_8,
            "ret_240m": ret_16,
            "rsi14": rsi,
            "last3": "".join(colors[-3:]),
            "reversal_hint": reversal_hint,
        },
        "note": "本地轻量模型，仅用于快速筛选；实盘前仍要结合盘口、流动性和结算时间。",
    }


def fmt_kline_time(row):
    return datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc).astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M 北京时间")


def run_reversal_backtest_from_rows(rows, mode, initial_usdc, max_layers, entry_price, fee_rate=0.07):
    if len(rows) < 10:
        raise ValueError("K 线数量不足，无法回测。")
    profile = reversal_profile(mode)
    colors = [kline_color(row) for row in rows]
    sizing = reversal_stakes(initial_usdc, entry_price, max_layers, fee_rate)
    stakes = sizing["stakes"]
    target_profit = sizing["target_profit"]
    loss_factor = sizing["loss_factor"]
    cycles = []
    i = 2
    while i < len(colors) - 1:
        is_new_trigger = colors[i - 2:i + 1] == [profile["trigger_color"]] * 3 and (i < 3 or colors[i - 3] != profile["trigger_color"])
        if not is_new_trigger:
            i += 1
            continue
        trigger_index = i
        pnl = None
        rows_used = []
        last_trade_index = trigger_index
        for layer, stake in enumerate(stakes, start=1):
            trade_index = trigger_index + layer
            if trade_index >= len(colors):
                break
            last_trade_index = trade_index
            win = colors[trade_index] == profile["win_color"]
            rows_used.append({
                "layer": layer,
                "time": fmt_kline_time(rows[trade_index]),
                "stake": stake,
                "win": win,
                "color": colors[trade_index],
            })
            if win:
                pnl = target_profit
                break
        if pnl is None and len(rows_used) == len(stakes):
            pnl = -sum(loss_factor * stake for stake in stakes[:len(rows_used)])
        elif pnl is None:
            break
        cycles.append({
            "trigger": fmt_kline_time(rows[trigger_index]),
            "pnl": pnl,
            "win": pnl > 0,
            "layers": len(rows_used),
            "rows": rows_used,
        })
        i = last_trade_index + 1
        while i < len(colors) and colors[i] == profile["trigger_color"]:
            i += 1

    total_pnl = sum(item["pnl"] for item in cycles)
    wins = sum(1 for item in cycles if item["win"])
    losses = len(cycles) - wins
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for item in cycles:
        equity += item["pnl"]
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return {
        "mode": profile["mode"],
        "label": profile["label"],
        "from": fmt_kline_time(rows[0]),
        "to": fmt_kline_time(rows[-1]),
        "kline_count": len(rows),
        "cycles": len(cycles),
        "wins": wins,
        "losses": losses,
        "win_rate": wins / len(cycles) if cycles else 0.0,
        "total_pnl": total_pnl,
        "max_drawdown": max_drawdown,
        "sizing": sizing,
        "recent": cycles[-10:],
    }
