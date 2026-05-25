import asyncio
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import aiohttp
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions, Side
from py_clob_client_v2.client import ClobClient
from py_clob_client_v2.clob_types import ApiCreds

from auth import UserStore
from core import (
    MarketData,
    REVERSAL_MODE_GREEN_DOWN,
    REVERSAL_MODE_RED_UP,
    fmt_kline_time,
    local_btc_probability_from_rows,
    reversal_stakes,
    run_reversal_backtest_from_rows,
)
from vault import VaultStore


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Polymarket VPS Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

market_data = MarketData()
vault = VaultStore()
user_store = UserStore()
jobs = {}
BEIJING_TZ = timezone(timedelta(hours=8))
CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137
report_task = None


class VaultBlob(BaseModel):
    version: int = 1
    kdf: str
    iterations: int
    salt: str
    nonce: str
    ciphertext: str


class UnlockRequest(BaseModel):
    passphrase: str = Field(min_length=8)


class AuthRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=10)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6)


class CapitalRequest(BaseModel):
    initial_usdc: float = Field(gt=0, default=5)
    max_layers: int = Field(ge=1, le=10, default=3)
    entry_price: float = Field(gt=0, lt=1, default=0.5)
    fee_rate: float = Field(ge=0, le=0.5, default=0.07)


class BacktestRequest(CapitalRequest):
    mode: str = REVERSAL_MODE_RED_UP
    days: int = Field(ge=1, le=1000, default=365)


class PredictRequest(BaseModel):
    market: dict = Field(default_factory=dict)
    days: int = Field(ge=1, le=14, default=3)


class LiveStartRequest(CapitalRequest):
    mode: str = REVERSAL_MODE_RED_UP
    max_hours: float = Field(gt=0, le=168, default=24)
    dry_run: bool = True


class ManualOrderRequest(BaseModel):
    market: dict = Field(default_factory=dict)
    direction: str = Field(pattern="^(UP|DOWN)$")
    side: str = Field(pattern="^(BUY|SELL)$", default="BUY")
    usdc_amount: float = Field(gt=0, default=5)
    size: float | None = Field(default=None, gt=0)
    max_price: float = Field(gt=0, lt=1, default=0.55)
    price: float | None = Field(default=None, gt=0, lt=1)


class PositionSellRequest(BaseModel):
    token_id: str = Field(min_length=10)
    size: float = Field(gt=0)
    price: float = Field(gt=0, lt=1)
    tick_size: str = "0.01"
    title: str = ""
    outcome: str = ""
    slug: str = ""


class NotificationSettings(BaseModel):
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    daily_report_time: str = Field(default="21:30", pattern=r"^\d{2}:\d{2}$")


class ModelSettings(BaseModel):
    preferred_provider: str = "minimax_cn"
    preferred_model: str = "MiniMax-M2.7"
    custom_base_url: str = ""
    custom_model: str = ""


MODEL_PROVIDERS = {
    "minimax_cn": {"label": "MiniMax 国内版", "base_url": "https://api.minimaxi.com/v1", "default_model": "MiniMax-M2.7"},
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "default_model": "deepseek-chat"},
    "qwen": {"label": "阿里 Qwen", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "default_model": "qwen-plus"},
    "kimi": {"label": "Kimi", "base_url": "https://api.moonshot.cn/v1", "default_model": "moonshot-v1-8k"},
    "zhipu": {"label": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4", "default_model": "glm-4-flash"},
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1", "default_model": "gpt-4.1-mini"},
    "anthropic": {"label": "Anthropic Claude", "base_url": "https://api.anthropic.com", "default_model": "claude-3-5-sonnet-latest"},
    "google": {"label": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta", "default_model": "gemini-1.5-pro"},
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "default_model": "openai/gpt-4o-mini"},
}


def validate_mode(mode: str):
    if mode not in {REVERSAL_MODE_RED_UP, REVERSAL_MODE_GREEN_DOWN}:
        raise HTTPException(status_code=400, detail="未知策略模式")


def current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录。")
    username = user_store.user_for_token(authorization.removeprefix("Bearer ").strip())
    if not username:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录。")
    return username


def admin_user(username: str = Depends(current_user)):
    user = user_store.public_user(username)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限。")
    if user.get("password_change_required"):
        raise HTTPException(status_code=403, detail="管理员首次登录必须先修改默认密码。")
    return username


def regular_user(username: str = Depends(current_user)):
    user = user_store.public_user(username)
    if user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="管理员账号只用于后台管理，不能进行交易或保存交易凭证。")
    if user.get("status") != "approved":
        raise HTTPException(status_code=403, detail="账号正在等待管理员审批。")
    if user.get("password_change_required"):
        raise HTTPException(status_code=403, detail="请先修改初始密码。")
    return username


def job_id_for(username: str, mode: str):
    return f"{username}:reversal-live:{mode}"


def user_jobs(username: str):
    return {job_id: job for job_id, job in jobs.items() if job.get("user") == username}


def float_or_zero(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def price_decimals(tick_size: str) -> int:
    if "." not in tick_size:
        return 0
    return len(tick_size.rstrip("0").split(".", 1)[1])


def clamp_price(price: float, tick_size: str) -> float:
    tick = float(tick_size or "0.01")
    return round(min(max(price, tick), 1.0 - tick), price_decimals(str(tick_size or "0.01")))


def book_level_value(level, key: str):
    if isinstance(level, dict):
        return level.get(key)
    return getattr(level, key, None)


def validate_credentials(credentials: dict):
    if not credentials.get("priv_key"):
        raise ValueError("缺少 Polygon 钱包私钥。")
    signature_type = int(credentials.get("signature_type") or 3)
    if signature_type != 0 and not credentials.get("funder"):
        raise ValueError("签名类型不是 0 时必须填写 Funder 地址。")
    api_values = [credentials.get("api_key"), credentials.get("secret"), credentials.get("passphrase")]
    if any(api_values) and not all(api_values):
        raise ValueError("CLOB API Key、Secret、Passphrase 要么都填，要么都留空自动派生。")


async def clob_client_for(username: str):
    credentials = vault.credentials(username)
    validate_credentials(credentials)
    if credentials.get("api_key"):
        api_creds = ApiCreds(credentials["api_key"], credentials["secret"], credentials["passphrase"])
    else:
        temp = ClobClient(host=CLOB_HOST, chain_id=CHAIN_ID, key=credentials["priv_key"], retry_on_error=True)
        api_creds = await asyncio.to_thread(temp.derive_api_key)
    kwargs = {
        "host": CLOB_HOST,
        "chain_id": CHAIN_ID,
        "key": credentials["priv_key"],
        "creds": api_creds,
        "retry_on_error": True,
    }
    signature_type = int(credentials.get("signature_type") or 3)
    if signature_type != 0:
        kwargs["signature_type"] = signature_type
        kwargs["funder"] = credentials.get("funder")
    return ClobClient(**kwargs), credentials


async def best_quote(client, token_id: str):
    orderbook = await asyncio.wait_for(asyncio.to_thread(client.get_order_book, token_id), timeout=15)
    raw_bids = orderbook.get("bids", []) if isinstance(orderbook, dict) else getattr(orderbook, "bids", None) or []
    raw_asks = orderbook.get("asks", []) if isinstance(orderbook, dict) else getattr(orderbook, "asks", None) or []
    tick_size = str((orderbook.get("tick_size") if isinstance(orderbook, dict) else getattr(orderbook, "tick_size", None)) or "0.01")
    bids = [float(book_level_value(level, "price")) for level in raw_bids if book_level_value(level, "price") is not None]
    asks = [float(book_level_value(level, "price")) for level in raw_asks if book_level_value(level, "price") is not None]
    return {"bid": max(bids) if bids else None, "ask": min(asks) if asks else None, "tick_size": tick_size}


async def fetch_positions_for_credentials(credentials: dict):
    user = credentials.get("funder") or credentials.get("address") or ""
    if not user:
        return []
    params = {"user": user, "limit": "80", "sizeThreshold": "0", "sortBy": "CURRENT", "sortDirection": "DESC"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12), headers={"User-Agent": "Mozilla/5.0"}) as session:
        async with session.get("https://data-api.polymarket.com/positions", params=params) as response:
            if response.status != 200:
                raise RuntimeError(f"持仓接口 HTTP {response.status}")
            data = await response.json()
    return data if isinstance(data, list) else []


def position_summary(positions):
    visible = [p for p in positions if float_or_zero(p.get("size")) > 0.000001]
    total_value = sum(float_or_zero(p.get("currentValue")) for p in visible)
    total_pnl = sum(float_or_zero(p.get("cashPnl")) for p in visible)
    total_cost = total_value - total_pnl
    total_pct = (total_pnl / total_cost * 100.0) if abs(total_cost) > 0.000001 else 0.0
    return {
        "count": len(visible),
        "total_value": total_value,
        "total_pnl": total_pnl,
        "total_pct": total_pct,
        "positions": visible,
    }


def report_markdown(username: str, summary: dict, user_job_map: dict):
    rows = [
        "### Polymarket 每日交易报告",
        "",
        f"- 账号: `{username}`",
        f"- 时间: `{datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M 北京时间')}`",
        f"- 持仓数: `{summary['count']}`",
        f"- 总现值: `{summary['total_value']:.2f}` USDC",
        f"- 总浮盈亏: `{summary['total_pnl']:+.2f}` USDC (`{summary['total_pct']:+.2f}%`)",
        f"- 运行任务: `{sum(1 for job in user_job_map.values() if job.get('status') == 'running')}`",
    ]
    if summary["positions"]:
        rows.append("")
        rows.append("主要持仓:")
        for p in summary["positions"][:8]:
            rows.append(
                f"- {p.get('outcome', '')} {float_or_zero(p.get('size')):.2f} 份 | "
                f"均价 {float_or_zero(p.get('avgPrice')):.4f} | "
                f"现价 {float_or_zero(p.get('curPrice')):.4f} | "
                f"浮盈亏 {float_or_zero(p.get('cashPnl')):+.2f} USDC | "
                f"{str(p.get('title', ''))[:80]}"
            )
    return "\n".join(rows)


async def push_server_chan(sendkey: str, title: str, content: str):
    if not sendkey:
        return {"skipped": True}
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        async with session.post(url, data={"title": title, "desp": content}) as response:
            return {"status": response.status, "text": (await response.text())[:300]}


async def push_telegram(bot_token: str, chat_id: str, content: str):
    if not bot_token or not chat_id:
        return {"skipped": True}
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        async with session.post(url, json={"chat_id": chat_id, "text": content[:3900], "parse_mode": "Markdown"}) as response:
            return {"status": response.status, "text": (await response.text())[:300]}


async def notify_user(username: str, title: str, content: str):
    settings = user_store.settings(username)
    credentials = {}
    try:
        credentials = vault.credentials(username)
    except Exception:
        pass
    sendkey = credentials.get("sendkey") or settings.get("sendkey") or ""
    results = {}
    try:
        results["server_chan"] = await push_server_chan(sendkey, title, content)
    except Exception as exc:
        results["server_chan"] = {"error": str(exc)}
    try:
        results["telegram"] = await push_telegram(settings.get("telegram_bot_token", ""), settings.get("telegram_chat_id", ""), content)
    except Exception as exc:
        results["telegram"] = {"error": str(exc)}
    return results


async def build_account_report(username: str):
    if not vault.status(username)["unlocked"]:
        return None
    credentials = vault.credentials(username)
    positions = await fetch_positions_for_credentials(credentials)
    summary = position_summary(positions)
    return report_markdown(username, summary, user_jobs(username))


async def daily_report_loop():
    last_sent = {}
    while True:
        now = datetime.now(BEIJING_TZ)
        hhmm = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")
        for user in user_store.list_users():
            username = user["username"]
            settings = user_store.settings(username)
            report_time = settings.get("daily_report_time") or "21:30"
            key = f"{username}:{today}:{report_time}"
            if report_time == hhmm and last_sent.get(username) != key:
                last_sent[username] = key
                try:
                    content = await build_account_report(username)
                    if content:
                        await notify_user(username, "Polymarket 每日交易报告", content)
                except Exception:
                    pass
        await asyncio.sleep(30)


@app.on_event("startup")
async def startup_tasks():
    global report_task
    if report_task is None:
        report_task = asyncio.create_task(daily_report_loop())


@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/admin")
async def admin_index():
    return FileResponse(FRONTEND_DIR / "admin.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "users": len(user_store.users)}


@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    try:
        user_store.register(req.username, req.password)
        user = user_store.public_user(req.username)
        return {"ok": True, "pending_approval": True, **user}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/login")
async def login(req: AuthRequest):
    try:
        token = user_store.login(req.username, req.password)
        user = user_store.public_user(req.username)
        return {"ok": True, "token": token, **user}
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/api/auth/logout")
async def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        user_store.logout(authorization.removeprefix("Bearer ").strip())
    return {"ok": True}


@app.post("/api/auth/change_password")
async def change_password(req: ChangePasswordRequest, username: str = Depends(current_user)):
    try:
        user_store.change_password(username, req.old_password, req.new_password)
        return {"ok": True, **user_store.public_user(username)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/me")
async def me(username: str = Depends(current_user)):
    user = user_store.public_user(username)
    return {
        "username": username,
        "role": user["role"],
        "password_change_required": user["password_change_required"],
        "vault": vault.status(username),
        "jobs": user_jobs(username),
        "settings": user_store.settings(username),
    }


@app.get("/api/admin/users")
async def admin_users(_: str = Depends(admin_user)):
    return {"users": user_store.list_users()}


@app.delete("/api/admin/users/{target_username}")
async def admin_delete_user(target_username: str, username: str = Depends(admin_user)):
    if target_username == username:
        raise HTTPException(status_code=400, detail="不能删除当前登录的管理员账号。")
    try:
        for job_id, job in list(jobs.items()):
            if job.get("user") == target_username:
                job["status"] = "stopped"
                jobs.pop(job_id, None)
        vault.lock(target_username)
        user_store.delete_user(target_username)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/admin/users/{target_username}/approve")
async def admin_approve_user(target_username: str, _: str = Depends(admin_user)):
    try:
        user_store.approve_user(target_username)
        return {"ok": True, "user": user_store.public_user(target_username)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/admin/users/{target_username}/reject")
async def admin_reject_user(target_username: str, _: str = Depends(admin_user)):
    try:
        user_store.reject_user(target_username)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/admin/cache/clear")
async def admin_clear_cache(_: str = Depends(admin_user)):
    market_data.clear_cache()
    return {"ok": True, "message": "缓存已清理。"}


@app.get("/api/admin/jobs")
async def admin_jobs(_: str = Depends(admin_user)):
    return {"jobs": jobs}


@app.post("/api/settings/notifications")
async def save_notification_settings(req: NotificationSettings, username: str = Depends(regular_user)):
    settings = user_store.update_settings(username, req.model_dump())
    return {"ok": True, "settings": settings}


@app.get("/api/settings/notifications")
async def get_notification_settings(username: str = Depends(regular_user)):
    settings = {"telegram_bot_token": "", "telegram_chat_id": "", "daily_report_time": "21:30"}
    settings.update(user_store.settings(username))
    return settings


@app.post("/api/settings/model")
async def save_model_settings(req: ModelSettings, username: str = Depends(regular_user)):
    payload = req.model_dump()
    if payload["preferred_provider"] == "custom":
        if not payload["custom_base_url"] or not payload["custom_model"]:
            raise HTTPException(status_code=400, detail="自定义接口需要填写 Base URL 和模型名。")
    else:
        provider = MODEL_PROVIDERS.get(payload["preferred_provider"])
        if not provider:
            raise HTTPException(status_code=400, detail="未知模型服务。")
        payload["custom_base_url"] = ""
        payload["custom_model"] = ""
        payload["preferred_model"] = payload["preferred_model"] or provider["default_model"]
    settings = user_store.update_settings(username, {"model": payload})
    return {"ok": True, "model": settings.get("model") or {}}


@app.get("/api/settings/model")
async def get_model_settings(username: str = Depends(regular_user)):
    model = {"preferred_provider": "minimax_cn", "preferred_model": MODEL_PROVIDERS["minimax_cn"]["default_model"], "custom_base_url": "", "custom_model": ""}
    model.update((user_store.settings(username).get("model") or {}))
    provider = MODEL_PROVIDERS.get(model["preferred_provider"])
    return {
        **model,
        "providers": MODEL_PROVIDERS,
        "effective_base_url": provider["base_url"] if provider else model.get("custom_base_url", ""),
        "effective_model": model.get("custom_model") if model["preferred_provider"] == "custom" else (model.get("preferred_model") or provider["default_model"]),
    }


@app.get("/api/vault/status")
async def vault_status(username: str = Depends(regular_user)):
    return vault.status(username)


@app.post("/api/vault/save")
async def save_vault(blob: VaultBlob, username: str = Depends(regular_user)):
    try:
        vault.save_encrypted_blob(blob.model_dump(), username)
        vault.lock(username)
        return {"ok": True, "status": vault.status(username)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/vault/unlock")
async def unlock_vault(req: UnlockRequest, username: str = Depends(regular_user)):
    try:
        loaded = vault.unlock(req.passphrase, username)
        return {"ok": True, "loaded": loaded, "status": vault.status(username)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"解锁失败: {exc}") from exc


@app.post("/api/vault/lock")
async def lock_vault(username: str = Depends(regular_user)):
    vault.lock(username)
    return {"ok": True, "status": vault.status(username)}


@app.get("/api/markets/quick")
async def quick_markets():
    try:
        return {"items": await market_data.fetch_quick_btc_markets()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/trading/snapshot")
async def trading_snapshot(username: str = Depends(regular_user)):
    if not vault.status(username)["unlocked"]:
        raise HTTPException(status_code=400, detail="请先解锁凭证。")
    try:
        client, credentials = await clob_client_for(username)
        positions = await fetch_positions_for_credentials(credentials)
        summary = position_summary(positions)
        balance = None
        try:
            balance = await asyncio.wait_for(asyncio.to_thread(client.get_balance_allowance, {}), timeout=12)
        except Exception as exc:
            balance = {"warning": f"余额接口不可用: {exc}"}
        return {"summary": summary, "balance": balance, "refreshed_at": datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S 北京时间")}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/trading/manual_order")
async def manual_order(req: ManualOrderRequest, username: str = Depends(regular_user)):
    if not vault.status(username)["unlocked"]:
        raise HTTPException(status_code=400, detail="请先解锁凭证。")
    try:
        client, credentials = await clob_client_for(username)
        token_id = req.market.get("yes_id") if req.direction == "UP" else req.market.get("no_id")
        if not token_id:
            raise ValueError("缺少选中市场 token id。")
        quote = await best_quote(client, token_id)
        if req.side == "BUY":
            market_price = quote["ask"]
            if market_price is None:
                raise ValueError("订单簿没有可买入卖价。")
            if market_price > req.max_price:
                raise ValueError(f"盘口卖价 {market_price:.4f} 高于最高价 {req.max_price:.4f}，已拒绝下单。")
            price = clamp_price(req.price or market_price, quote["tick_size"])
            size = req.usdc_amount / price
            side = Side.BUY
        else:
            market_price = quote["bid"]
            if market_price is None:
                raise ValueError("订单簿没有可卖出买价。")
            price = clamp_price(req.price or market_price, quote["tick_size"])
            size = req.size or req.usdc_amount / price
            side = Side.SELL
        if size < 5:
            raise ValueError(f"下单数量 {size:.4f} 小于 5 份最小要求。")
        resp = await asyncio.wait_for(
            asyncio.to_thread(
                client.create_and_post_order,
                order_args=OrderArgs(token_id=str(token_id), price=float(price), size=float(size), side=side),
                options=PartialCreateOrderOptions(tick_size=quote["tick_size"]),
                order_type=OrderType.GTC,
                post_only=False,
            ),
            timeout=25,
        )
        if isinstance(resp, dict) and resp.get("success") is False:
            raise ValueError(f"交易所拒绝订单: {resp}")
        await asyncio.sleep(1.5)
        positions = await fetch_positions_for_credentials(credentials)
        summary = position_summary(positions)
        content = report_markdown(username, summary, user_jobs(username))
        content = f"### Polymarket 手动交易结果\n\n- 操作: `{req.side} {req.direction}`\n- 价格: `{price:.4f}`\n- 数量: `{size:.4f}`\n- 市场: {req.market.get('question', '')}\n\n{content}"
        notification = await notify_user(username, "Polymarket 手动交易结果", content)
        return {"ok": True, "order": resp, "price": price, "size": size, "quote": quote, "summary": summary, "notification": notification}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/trading/sell_position")
async def sell_position(req: PositionSellRequest, username: str = Depends(regular_user)):
    if not vault.status(username)["unlocked"]:
        raise HTTPException(status_code=400, detail="请先解锁凭证。")
    try:
        client, credentials = await clob_client_for(username)
        price = clamp_price(req.price, req.tick_size)
        resp = await asyncio.wait_for(
            asyncio.to_thread(
                client.create_and_post_order,
                order_args=OrderArgs(token_id=req.token_id, price=float(price), size=float(req.size), side=Side.SELL),
                options=PartialCreateOrderOptions(tick_size=req.tick_size),
                order_type=OrderType.GTC,
                post_only=False,
            ),
            timeout=25,
        )
        if isinstance(resp, dict) and resp.get("success") is False:
            raise ValueError(f"交易所拒绝订单: {resp}")
        positions = await fetch_positions_for_credentials(credentials)
        summary = position_summary(positions)
        content = f"### Polymarket 限价卖出结果\n\n- 市场: {req.title}\n- 方向: `{req.outcome}`\n- 价格: `{price:.4f}`\n- 数量: `{req.size:.4f}`\n\n{report_markdown(username, summary, user_jobs(username))}"
        notification = await notify_user(username, "Polymarket 限价卖出结果", content)
        return {"ok": True, "order": resp, "summary": summary, "notification": notification}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/reports/send_now")
async def send_report_now(username: str = Depends(regular_user)):
    try:
        content = await build_account_report(username)
        if not content:
            raise ValueError("请先解锁凭证后再生成报告。")
        notification = await notify_user(username, "Polymarket 每日交易报告", content)
        return {"ok": True, "report": content, "notification": notification}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/strategy/predict")
async def strategy_predict(req: PredictRequest):
    try:
        rows = await market_data.fetch_btc_15m_klines(req.days)
        return local_btc_probability_from_rows(rows, req.market)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/strategy/capital")
async def strategy_capital(req: CapitalRequest):
    return reversal_stakes(req.initial_usdc, req.entry_price, req.max_layers, req.fee_rate)


@app.post("/api/strategy/backtest")
async def strategy_backtest(req: BacktestRequest):
    validate_mode(req.mode)
    try:
        rows = await market_data.fetch_btc_15m_klines(req.days)
        return run_reversal_backtest_from_rows(rows, req.mode, req.initial_usdc, req.max_layers, req.entry_price, req.fee_rate)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def dry_run_live_job(job_id: str, config: dict):
    jobs[job_id]["status"] = "running"
    jobs[job_id]["events"].append("任务 dry-run 已启动。它只写入任务页状态，不会覆盖回测页结果，也不会自动提交真实订单。")
    end_time = asyncio.get_running_loop().time() + config["max_hours"] * 3600
    while jobs[job_id].get("status") == "running" and asyncio.get_running_loop().time() < end_time:
        try:
            rows = await market_data.fetch_btc_15m_klines(3)
            jobs[job_id]["last_kline"] = fmt_kline_time(rows[-1]) if rows else None
            jobs[job_id]["events"].append(f"心跳: 已读取 {len(rows)} 根 15m K线，最后一根 {jobs[job_id]['last_kline']}")
        except Exception as exc:
            jobs[job_id]["events"].append(f"读取失败: {exc}")
        jobs[job_id]["events"] = jobs[job_id]["events"][-100:]
        await asyncio.sleep(60)
    if jobs[job_id].get("status") == "running":
        jobs[job_id]["status"] = "finished"


@app.post("/api/strategy/live/start")
async def live_start(req: LiveStartRequest, username: str = Depends(regular_user)):
    validate_mode(req.mode)
    if not req.dry_run and not vault.status(username)["unlocked"]:
        raise HTTPException(status_code=400, detail="实盘需要先解锁加密凭证。")
    job_id = job_id_for(username, req.mode)
    if jobs.get(job_id, {}).get("status") == "running":
        raise HTTPException(status_code=409, detail="该方向策略任务已经在运行。")
    config = req.model_dump()
    jobs[job_id] = {
        "id": job_id,
        "status": "starting",
        "user": username,
        "mode": req.mode,
        "config": config,
        "events": [],
        "started_at": datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S 北京时间"),
    }
    if not req.dry_run:
        jobs[job_id]["status"] = "blocked"
        jobs[job_id]["events"].append("真实下单模块留有安全闸门：部署后请先用 dry-run 跑通，再显式接入交易执行。")
        raise HTTPException(status_code=400, detail="真实下单安全闸门未开启，本版本默认只允许 dry-run。")
    asyncio.create_task(dry_run_live_job(job_id, config))
    return {"ok": True, "job": jobs[job_id]}


@app.post("/api/strategy/live/stop")
async def live_stop(mode: str | None = None, username: str = Depends(regular_user)):
    stopped = []
    for job_id, job in user_jobs(username).items():
        if mode and job.get("mode") != mode:
            continue
        job["status"] = "stopped"
        job.setdefault("events", []).append("已请求停止。")
        stopped.append(job_id)
    return {"ok": True, "stopped": stopped}


@app.get("/api/strategy/live/status")
async def live_status(username: str = Depends(regular_user)):
    return {"jobs": user_jobs(username)}
