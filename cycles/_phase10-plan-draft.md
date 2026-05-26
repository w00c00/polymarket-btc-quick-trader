# Plan: Phase 10 — Periodic account refresh (positions + USDC balance)

## Why

`VIRTUES-PLAN-ADDENDUM.md` Phase 10 (V1 / V3 / V7): today the user only sees positions after manually clicking 刷新持仓 (`refresh_positions_button_clicked` L2485). Between clicks the GUI is arbitrarily stale. The reversal-live loop opens / closes positions every layer; if `_flatten_cycle_positions` leaves a residual bag (Phase 5 corner case), the user has no passive way to notice. Worse, **no balance is displayed at all** — no USDC widget anywhere in `setup_ui`.

Phase 10 adds a 60 s self-scheduling Tk tick (same pattern as Phase 11 `_daily_report_tick` L2403) that fetches positions + USDC balance, paints a status label `余额: $X.XX | 持仓: N | 上次刷新: 12s 前` above the positions tree, and on transient failure preserves the previous values labeled `(stale 78s)` in orange.

The manual 刷新持仓 button stays unchanged — Phase 10 is additive. This phase is a hard prerequisite for the deferred 日内亏损熔断 / 余额最低保护 feature (ADDENDUM L40) and for Phase 12 (`daily_max_exposure_usdc` enforcement). Phase 10 itself does NOT implement any circuit breaker.

## Schema 实证 — USDC balance endpoint (live-verify-owed)

**WebFetch was unavailable during plan drafting; implementer MUST verify before coding** (Lesson 1):

```bash
curl -s "https://docs.polymarket.com/api-reference/core/get-user-positions-value.md" | head -120
curl -s "https://docs.polymarket.com/sitemap.xml" | grep -iE "balance|value|holdings"
curl -s "https://data-api.polymarket.com/value?user=$POLY_FUNDER_ADDRESS" | python -m json.tool
```

**Candidate A — data-api `/value`** (matches `fetch_positions` L2086 pattern): `GET data-api.polymarket.com/value?user=<addr>` → `[{"user","value"}]`. Likely positions-value, not free USDC.

**Candidate B — Polygon JSON-RPC `eth_call(USDC.balanceOf(funder))`** (free wallet USDC): POST `https://polygon-rpc.com`, USDC contract `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`, selector `0x70a08231 + padded_addr` → hex / 1e6.

If A returns free wallet USDC, use A; else use B. Plan body assumes B. Helper signature symmetric — swap mechanical. Implementer fills `## 外部 schema 来源` table BEFORE coding.

## Files in scope (whitelist)

- `poly_mm_pro_max.py` — `_fetch_usdc_balance_onchain` async helper, `_periodic_account_refresh_tick` Tk callback, `_render_account_status` UI helper, one new label widget in `setup_ui`, one `root.after(...)` register in `__init__`.
- `tests/test_account_refresh.py` — **NEW**. ≥8 cases.

## Out of scope (explicit DON'T)

1. DO NOT modify `fetch_positions` (L2086), `_fetch_positions_raw` (L2109), or `render_positions` (L2498) — Phase 10 only consumes them and adds a label ABOVE the tree.
2. DO NOT modify `refresh_positions_button_clicked` (L2485) — manual button MUST keep working unchanged.
3. DO NOT implement any circuit breaker / `daily_max_exposure_usdc` — Phase 10 is read-only; that lands later.
4. DO NOT append balance to `trade_journal.csv` (Phase 9 frozen); DO NOT touch Phase 11 `_daily_report_tick` (independent `root.after` chain).
5. DO NOT introduce a daemon thread / `asyncio.create_task` / new dependency (`web3.py` forbidden) — reuse per-tick `asyncio.new_event_loop()` pattern from `_daily_report_tick`; raw aiohttp JSON-RPC POST only.
6. DO NOT change `_get_aiohttp_session` (Phase 7 frozen + final-patches `1b4e4a8`); DO NOT block on slow network — `aiohttp.ClientTimeout(total=12)` mandatory.
7. DO NOT change Server酱 push semantics.

## The change (literal spec)

### Step 1 — Add state fields in `__init__`

In `PolyQuickTrader.__init__` (~L138), after `self.live_results = []` and before `self.live_auto_enabled = False`:

```python
        # Phase 10: periodic account refresh state.
        self.account_last_balance_usdc: float | None = None
        self.account_last_positions_count: int | None = None
        self.account_last_refresh_ts: float | None = None
        self.account_last_error: str | None = None
        self._account_refresh_running: bool = False  # re-entry guard
```

### Step 2 — Add status label in `setup_ui`

In `setup_ui`, immediately BEFORE `self.positions_tree = ttk.Treeview(` (~L371). `pos_frame` is the existing `ttk.LabelFrame` containing the tree:

```python
        self.lbl_account_status = ttk.Label(
            pos_frame,
            text="余额: -- | 持仓: -- | 上次刷新: --",
            font=("Helvetica", 10),
            foreground="#6b7280",
        )
        self.lbl_account_status.pack(fill="x", pady=(0, 4))
```

### Step 3 — Add `_fetch_usdc_balance_onchain` async helper

Insert between `_fetch_positions_raw` (L2109-2130) and `_settle_from_positions` (L2132):

```python
    async def _fetch_usdc_balance_onchain(self) -> float:
        """
        Polygon JSON-RPC eth_call(USDC.balanceOf(funder)). Raises on
        transport/HTTP error so the caller can mark the previous value
        stale — never returns 0.0 to hide a network failure (V3 honesty).

        USDC.e (PoS) contract: 0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174
        balanceOf(address) selector: 0x70a08231
        Returns: float USDC (6 decimals applied).
        """
        addr = self.ent_funder.get().strip()
        if not addr or not addr.startswith("0x") or len(addr) != 42:
            raise ValueError(f"invalid funder address: {addr!r}")
        padded = addr.lower().replace("0x", "").rjust(64, "0")
        payload = {
            "jsonrpc": "2.0", "method": "eth_call",
            "params": [
                {"to": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
                 "data": "0x70a08231" + padded},
                "latest",
            ],
            "id": 1,
        }
        session = _get_aiohttp_session()
        async with session.post(
            "https://polygon-rpc.com", json=payload,
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=12),
        ) as response:
            if response.status != 200:
                raise RuntimeError(f"polygon RPC HTTP {response.status}")
            body = await response.json()
        result = body.get("result")
        if not isinstance(result, str) or not result.startswith("0x"):
            raise RuntimeError(f"polygon RPC malformed result: {body!r}")
        return int(result, 16) / 1_000_000.0
```

**If implementer's `curl` (Schema section) verifies a data-api free-balance endpoint, replace body with aiohttp GET — same return shape `(float, raises-on-failure)`.**

### Step 4 — Add `_periodic_account_refresh_tick`

Insert immediately AFTER `_daily_report_tick` (ends ~L2441):

```python
    def _periodic_account_refresh_tick(self):
        """Tk root.after callback. Every 60s fetches positions + USDC balance
        on a worker thread, then re-schedules. On failure, LAST known values
        are kept and label is annotated "(stale Xs)" — never zero out
        balance/positions (would visually mimic liquidation). Re-entry guard
        from Phase 11 _daily_report_tick."""
        try:
            if getattr(self, "_account_refresh_running", False):
                return
            self._account_refresh_running = True

            def worker():
                try:
                    loop = asyncio.new_event_loop()
                    try:
                        positions = loop.run_until_complete(self._fetch_positions_raw())
                        balance = loop.run_until_complete(self._fetch_usdc_balance_onchain())
                    finally:
                        loop.close()
                    self.account_last_balance_usdc = balance
                    self.account_last_positions_count = sum(
                        1 for p in positions
                        if self._float_or_zero(p.get("size")) > 0.000001
                    )
                    self.account_last_refresh_ts = time.time()
                    self.account_last_error = None
                    self.latest_positions = positions
                    self.root.after(0, lambda: self.render_positions(positions))
                except Exception as e:
                    self.account_last_error = f"{type(e).__name__}: {str(e)[:80]}"
                    self.logger.warning("账户定时刷新失败: %s", self.account_last_error)
                finally:
                    self._account_refresh_running = False
                    self.root.after(0, self._render_account_status)

            threading.Thread(target=worker, daemon=True).start()
        finally:
            self.root.after(60_000, self._periodic_account_refresh_tick)

    def _render_account_status(self):
        bal = self.account_last_balance_usdc
        npos = self.account_last_positions_count
        ts = self.account_last_refresh_ts
        bal_text = f"${bal:.2f}" if bal is not None else "--"
        npos_text = str(npos) if npos is not None else "--"
        if ts is None:
            ago_text, color = "--", "#6b7280"
        else:
            ago = max(0, int(time.time() - ts))
            stale = self.account_last_error is not None or ago > 120
            ago_text = f"{ago}s 前" + (f" (stale {ago}s)" if stale else "")
            color = "#f59e0b" if stale else "#10b981"
        self.lbl_account_status.configure(
            text=f"余额: {bal_text} | 持仓: {npos_text} | 上次刷新: {ago_text}",
            foreground=color,
        )
```

### Step 5 — Register the tick in `__init__`

After existing `self.root.after(5_000, self._daily_report_tick)` (L174):

```python
        # Phase 10: schedule periodic account refresh.
        self.root.after(2_000, self._periodic_account_refresh_tick)
```

### Step 6 — Tests (`tests/test_account_refresh.py`)

NEW file. ≥6 cases. Pattern: Tk-free `PolyQuickTrader.__new__` (per `tests/test_settle.py`), mock label widget via `types.SimpleNamespace(configure=lambda **k: None)`:

- `test_render_initial_state` — no ts → "--".
- `test_render_fresh` — ts=now, no error → green, "Xs 前" no stale.
- `test_render_stale_on_error` — error set → "(stale Xs)" + orange.
- `test_render_stale_on_age` — ts older than 120s → stale even without error.
- `test_balance_decode_hex` — monkeypatch session.post returns `{"result": "0xf4240"}` (= 1 USDC) → 1.0.
- `test_balance_invalid_addr_raises` — funder="" → ValueError (NOT silent 0).
- `test_balance_http_500_raises` — RuntimeError (NOT silent 0).
- `test_tick_reentry_guard` — set `_account_refresh_running=True`; call tick; assert no worker spawned.

## Verification commands

1. **New helper present**:
   ```bash
   grep -n "_fetch_usdc_balance_onchain\|_periodic_account_refresh_tick\|_render_account_status\|lbl_account_status" poly_mm_pro_max.py
   ```
   Expected: ≥7 lines.

2. **Tick registered**:
   ```bash
   grep -n "root.after.*_periodic_account_refresh_tick" poly_mm_pro_max.py
   ```
   Expected: ≥2 (initial + self-re-schedule).

3. **Manual button untouched** — `git diff poly_mm_pro_max.py` block enclosing `refresh_positions_button_clicked` must be empty.

4. **No new dependency**:
   ```bash
   git diff poly_mm_pro_max.py | grep -E "^\+(import|from)" | grep -vE "(asyncio|threading|time|tkinter|logging|aiohttp|datetime|os|csv)"
   ```
   Expected: empty.

5. **fetch_positions / `_fetch_positions_raw` line counts unchanged** vs main (capture baseline first).

6. **Tests pass**:
   ```bash
   .venv/bin/python -m pytest tests/test_account_refresh.py -v
   ```
   Expected: 8 passed.

7. **Sandbox-friendly variant** (Lesson 2):
   ```bash
   .venv/bin/python -m pytest tests/test_account_refresh.py -p no:cacheprovider --capture=no -q
   ```
   Expected: 8 passed.

8. **Full suite**:
   ```bash
   .venv/bin/python -m pytest tests/ -q
   ```
   Expected: 106 + 8 = 114 passed.

9. **Import OK**:
   ```bash
   .venv/bin/python -c "import poly_mm_pro_max; print('import ok')"
   ```

10. **Plan-coverage false-positive ack** (Lesson 5): `tests/test_account_refresh.py` is NEW — Codex `git diff --name-only` won't list it. Override pre-authorized if `git status --porcelain` shows `?? tests/test_account_refresh.py` AND pytest passes.

## Live verification owed (user, post-commit)

1. Launch GUI; within 2s status label shows `余额: $X.XX | 持仓: N | 上次刷新: 0s 前` in green.
2. Wait 60s → label updates; `Xs 前` resets near 0.
3. Unplug WiFi; wait 90s → label shows `(stale 90s)` in orange, positions tree retains last rows.
4. Re-plug WiFi; ≤60s → label returns to green.
5. Click 刷新持仓 → still works (logs `已刷新持仓: N 条`), label refreshes immediately.
6. After 30 min running, `lsof -p $(pgrep -f poly_mm_pro_max) | grep TCP | wc -l` stable (Phase 7 contract held).
7. Cross-check balance vs polymarket.com/portfolio "Available" — match to ±0.01 USDC.

## 外部 schema 来源 (implementer MUST fill before commit)

| Field | Source URL | Last checked |
|---|---|---|
| USDC contract (Polygon USDC.e) | <e.g. https://polygonscan.com/token/0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174> | <date> |
| `balanceOf(address)` selector `0x70a08231` | ERC-20 ABI standard (`keccak256("balanceOf(address)")[:4]`) | <date> |
| Polygon JSON-RPC endpoint | <e.g. https://chainlist.org/chain/137> | <date> |
| (If using data-api `/value`) endpoint schema | <fill> | <date> |

**Plan BLOCKED on filling this table** (Lesson 1).

## Relationship to other phases

- **Depends on** Phase 7 shared session (`bf562ba`), `_fetch_positions_raw` (Phase 4 final-patch `1b4e4a8`).
- **Unlocks** 日内亏损熔断 / 余额最低保护 (out of scope here) and Phase 12 (reads `account_last_balance_usdc`).
- **Coexists** with Phase 11 `_daily_report_tick`. **Does NOT modify** Phase 5 rollback or Phase 9 journal.
