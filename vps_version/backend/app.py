import asyncio
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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
    password: str = Field(min_length=10)


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


def job_id_for(username: str):
    return f"{username}:reversal-live"


@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "users": len(user_store.users)}


@app.post("/api/auth/register")
async def register(req: AuthRequest):
    try:
        user_store.register(req.username, req.password)
        token = user_store.login(req.username, req.password)
        return {"ok": True, "token": token, "username": req.username}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/login")
async def login(req: AuthRequest):
    try:
        token = user_store.login(req.username, req.password)
        return {"ok": True, "token": token, "username": req.username}
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/api/auth/logout")
async def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        user_store.logout(authorization.removeprefix("Bearer ").strip())
    return {"ok": True}


@app.get("/api/me")
async def me(username: str = Depends(current_user)):
    return {"username": username, "vault": vault.status(username), "job": jobs.get(job_id_for(username), {"status": "idle"})}


@app.get("/api/vault/status")
async def vault_status(username: str = Depends(current_user)):
    return vault.status(username)


@app.post("/api/vault/save")
async def save_vault(blob: VaultBlob, username: str = Depends(current_user)):
    try:
        vault.save_encrypted_blob(blob.model_dump(), username)
        vault.lock(username)
        return {"ok": True, "status": vault.status(username)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/vault/unlock")
async def unlock_vault(req: UnlockRequest, username: str = Depends(current_user)):
    try:
        loaded = vault.unlock(req.passphrase, username)
        return {"ok": True, "loaded": loaded, "status": vault.status(username)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"解锁失败: {exc}") from exc


@app.post("/api/vault/lock")
async def lock_vault(username: str = Depends(current_user)):
    vault.lock(username)
    return {"ok": True, "status": vault.status(username)}


@app.get("/api/markets/quick")
async def quick_markets():
    try:
        return {"items": await market_data.fetch_quick_btc_markets()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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
async def live_start(req: LiveStartRequest, username: str = Depends(current_user)):
    validate_mode(req.mode)
    if not req.dry_run and not vault.status(username)["unlocked"]:
        raise HTTPException(status_code=400, detail="实盘需要先解锁加密凭证。")
    job_id = job_id_for(username)
    if jobs.get(job_id, {}).get("status") == "running":
        raise HTTPException(status_code=409, detail="已有反转策略任务正在运行。")
    config = req.model_dump()
    jobs[job_id] = {"status": "starting", "user": username, "config": config, "events": []}
    if not req.dry_run:
        jobs[job_id]["status"] = "blocked"
        jobs[job_id]["events"].append("真实下单模块留有安全闸门：部署后请先用 dry-run 跑通，再显式接入交易执行。")
        raise HTTPException(status_code=400, detail="真实下单安全闸门未开启，本版本默认只允许 dry-run。")
    asyncio.create_task(dry_run_live_job(job_id, config))
    return {"ok": True, "job": jobs[job_id]}


@app.post("/api/strategy/live/stop")
async def live_stop(username: str = Depends(current_user)):
    job = jobs.get(job_id_for(username))
    if not job:
        return {"ok": True, "status": "idle"}
    job["status"] = "stopped"
    job["events"].append("已请求停止。")
    return {"ok": True, "job": job}


@app.get("/api/strategy/live/status")
async def live_status(username: str = Depends(current_user)):
    return jobs.get(job_id_for(username), {"status": "idle", "events": []})
