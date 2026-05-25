---
cycle_id: virtues-phase-4
commit_sha: 476a7b2
branch: ai-cycle/virtues-phase-4
parent: 38d7a62 (main)
date: 2026-05-26
includes_inline_patch: _fetch_positions_raw HTTP-failure isolation (Codex Phase 4 V8 warn)
---

# cycles/virtues-phase-4/agent.md

## Virtues (all PASS)
V1✓ V2✓ V3✓ V4✓ V5✓ V6✓ V7✓ V8✓ V9✓ — no gaps

## Files
- `poly_mm_pro_max.py` modify +84/-12 (new `_fetch_positions_raw`, new `_settle_from_positions`, `run_reversal_live_real` settlement logic replaced)
- `tests/test_settle.py` new +138 (9 regression tests including 2 HTTP-failure isolation cases)

## Key contract
`PolyQuickTrader._settle_from_positions(token_id, deadline_ts, stop_event=None) -> str`
Returns one of: `"win" | "loss" | "pending_timeout"`. Uses `_fetch_positions_raw` (raises on HTTP error) so transient network failures retry without advancing the absent-state machine.

## Codex review
verdict=BLOCK (false positive: same untracked-test issue) + 1 real warn (silent-empty conflation, **patched inline in same commit** via `_fetch_positions_raw`).

## Test results
`pytest tests/` → **27 passed** (12+6+9)

## Behavioral change
| Before | After |
|---|---|
| WIN = `kline_color(close_candle) == win_color` | WIN = `data-api Position.redeemable == True` |
| LOSS = `kline_color != win_color` OR market.ended | LOSS = `asset not in positions list` for 2 consecutive **successful** fetches |
| Network failure during settlement = silent + likely wrong | Network failure = retry with backoff, no false LOSS |
| Settlement deadline = none (loop forever or kline gives up) | Settlement deadline = `market.end_dt + 5min` else `now + 30min`; on timeout: ERROR log + Server酱 critical push + cycle halt |

## Schema source
data-api `/positions` Position schema — https://docs.polymarket.com/api-reference/core/get-current-positions-for-a-user (fetched 2026-05-26)

## Live verification owed (user)
Run a full reversal live cycle through to settlement. Expected:
- WIN log line: `单胜 (data-api redeemable=True): pnl≈+X.XXU`
- LOSS log line: `单负 (data-api 仓位归零): loss≈X.XXU`
- Server酱 push contains `结算: data-api redeemable` or `data-api 仓位归零` (not `1.0000` / `0.0000`)
