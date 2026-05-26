---
cycle_id: virtues-phase-10
commit_sha: abbeb36
branch: ai-cycle/virtues-phase-10
parent: 9f43507 (main)
date: 2026-05-26
includes_inline_patch: _apply_account_refresh ts preservation on all-fail per Codex Phase 10 V3 blocker
addendum_phase: yes (ADDENDUM, not main roadmap)
---

# cycles/virtues-phase-10/agent.md

## Virtues (all PASS)
V1✓ V2✓ V3✓ V4✓ V5✓ V6✓ V7✓ V8 n/a V9✓

## Files
- `poly_mm_pro_max.py` modify +~180 (3 new fetch helpers + tick + 4 support fns + Tk label + register)
- `tests/test_account_refresh.py` new +175 (11 cases)

## Key contracts
- `_fetch_positions_value() -> float | None` — data-api `/value`; None on failure, 0.0 on empty
- `_fetch_usdc_balance_onchain() -> float | None` — Polygon JSON-RPC eth_call(USDC.balanceOf); None on failure
- `_periodic_account_refresh_tick()` — Tk callback, 60s self-reschedule, race-locked via `_account_refresh_running`
- `_apply_account_refresh(positions, pos_value, balance)` — only advances `account_last_refresh_ts` when **at least one of pos_value or balance succeeded** (the inline patch)
- `_render_account_status_label(now)` — orange `#d97706` if age ≥ 90s, gray `#475569` otherwise

## Schema source
- data-api `/value`: https://docs.polymarket.com/api-reference/core/get-total-value-of-a-users-positions (positions market value, NOT free USDC)
- Polygon USDC.e: 0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174
- ERC20 `balanceOf` selector: 0x70a08231
- Public RPC: polygon-rpc.com
- Last checked: 2026-05-26

## Codex review
verdict=BLOCK (1 false-positive untracked test file + 1 real V3 blocker on ts preservation **patched inline**)

## Test results
`pytest tests/` → **117 passed** (Phase 1-11 + final-patches + Phase 10)

## Live verification owed (user)
1. 启 GUI → 3s 后看 `lbl_account_status` 显示 `余额: $X.XX | 持仓市值: $Y.YY | 持仓: N 条 | 刷新: Ns 前`
2. 等 60s → 数字滚动新一轮
3. 拔网线 → 90s 后 label 变橙色 `(stale Xs)`，旧数字保留
4. 把 `$X.XX` 跟 polymarket.com → Cash 对账
5. 把 `$Y.YY` 跟 polymarket.com/portfolio 总持仓值对账
