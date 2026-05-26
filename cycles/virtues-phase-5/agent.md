---
cycle_id: virtues-phase-5
commit_sha: 2ebc0a5
branch: ai-cycle/virtues-phase-5
parent: 9de9870 (main)
date: 2026-05-26
includes_inline_patch: buy-exception orphan probe via _fetch_positions_raw (Codex Phase 5 V3 blocker)
---

# cycles/virtues-phase-5/agent.md

## Virtues
V1✓ V2✓ V3✓ V4✓ V5✓ V6✓ V7 n/a V8✓ V9✓

## Files
- `poly_mm_pro_max.py` modify +85/-50 (cycle_open_positions accumulator + _flatten_cycle_positions helper + try/except wrap around layer body + 4 abort paths call flatten + buy-exception probe patch)
- `tests/test_rollback.py` new +175 (5 cases on flatten helper)

## Key contract
`_flatten_cycle_positions(open_positions, reason, cycle_count) -> list[dict]` — best-effort flatten of all positions opened in current cycle that haven't resolved. Marketable sell at `max(bid * 0.95, tick_value)`. Server酱 critical push at end.

Orphan probe (inline patch): outer try/except calls `_fetch_positions_raw` to detect current-layer orphan that buy_quick_market exception couldn't append normally.

## Codex review
verdict=BLOCK (false positive on plan_coverage for untracked test file + 1 real V3 blocker on current-layer orphan detection, **patched inline**, + 1 deferred warn on integration tests).

## Test results
`pytest tests/` → **47 passed** (12+6+10+9+5+5)

## What's NOT tested
Integration tests for `run_reversal_live_real` itself would require mocking Tk root + asyncio loop + 8+ method dependencies. Deferred to live spike. The flatten helper IS unit-tested (5 cases).

## Live verification owed (user)
Stub: monkeypatch `fetch_market_by_slug` returns None on 2nd layer call after a real layer-1 buy at 0.5 USDC. Expect:
1. Layer 1 fills (real fill via Phase 1)
2. Layer 2 lookup fails → log `rollback layer 1 卖出: ...`
3. Server酱 push `⚠️ 周期回滚`
4. polymarket.com/portfolio: layer-1 position closed / sell order resting

Also worth: monkeypatch `_post_signed_order_with_retry` to raise RuntimeError after letting one fake order land → exercise the buy-exception probe path → expect log `layer N 异常时仓位仍在 size=X，加入回滚`.

## Schema source
N/A (uses Phase 4's data-api Position schema; no new external API).
