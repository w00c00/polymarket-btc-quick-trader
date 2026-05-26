# cycles/_final-review.md — 完整路线图收尾 + Codex final review

> 2026-05-26 收尾记录。所有 10 个主体 phase land 后，跑了一次 `codex review --base origin/main` 全 branch review，找到 3 个 cross-phase issue，已全部 inline 修。

## 路线图全景

```
main:  
  1b4e4a8  final-patches: 3 cross-phase fixes per Codex final review
  0e8d902  docs(cycles): virtues-phase-11 handoff
  874fe25  Phase 11: daily report (aggregator + Tk tick + Server酱)
  18299d7  docs(cycles): virtues-phase-8 handoff
  1c5cb8d  Phase 8: pure-helper regression tests (29 cases + martingale invariant)
  caeb837  docs(cycles): virtues-phase-7 handoff
  bf562ba  Phase 7: shared aiohttp.ClientSession keyed by loop id
  f0cc339  docs(cycles): virtues-phase-6 handoff
  6f422a0  Phase 6: honest error surfacing (POLY_1271 + MiniMax + status)
  cfac9db  docs(cycles): Phase 7/8/11 plan drafts (subagent)
  3091a80  docs(cycles): virtues-phase-5 handoff
  2ebc0a5  Phase 5: cycle rollback on mid-cycle aborts (BLOCKER #4)
  38d7a62  docs(cycles): lessons 4+5
  1572027  docs(cycles): virtues-phase-3 handoff
  1c891f9  Phase 3: lock-file race + OSError harden (BLOCKER #5)
  a60f760  docs(cycles): virtues-phase-1 handoff
  c7b1486  Phase 1: extract verified buy fill /1e6 scaling (BLOCKER #1)
  561522c  Phase 2 research (server-dedup hypothesis)
  ...   (Phase 9 / Phase 4 / Phase 2 earlier)
```

## BLOCKER 全部状态

| # | Phase | 状态 |
|---|---|---|
| #1 真实 fill | Phase 1 (`c7b1486`) | ✅ |
| #2 仓位真实判定 | Phase 4 (`476a7b2`) + final-patches | ✅ |
| #3 timeout-retry | Phase 2 (`bcf7559`) | ✅ (live spike 仍欠) |
| #4 cycle rollback | Phase 5 (`2ebc0a5`) | ✅ |
| #5 lock race | Phase 3 (`1c891f9`) | ✅ |

## Non-BLOCKER phases

| Phase | 状态 |
|---|---|
| 6 (honest err) | ✅ `6f422a0` |
| 7 (shared aiohttp) | ✅ `bf562ba` + final-patches |
| 8 (helper tests) | ✅ `1c5cb8d` |
| 9 (journal + heartbeat + NaN) | ✅ `d195ab9` |
| 11 (daily report) | ✅ `874fe25` + final-patches |

## ADDENDUM phases (未在主路线图)

| Phase | 状态 |
|---|---|
| 10 (余额定时刷新) | ⏸ 未实施 — VIRTUES-PLAN-ADDENDUM.md 提案 |
| 12 (双开并行) | ⏸ 未实施 — HIGH RISK，需先全 phase live verification |

## 测试规模

- pytest tests/ → **106 passed**
- 文件：test_pure.py (12) + test_lock.py (6) + test_settle.py (10, +1 final) + test_observability.py (10) + test_retry_post.py (5) + test_rollback.py (5) + test_session.py (5) + test_helpers.py (29) + test_honesty.py (14) + test_daily_report.py (10, +2 final)

## Codex final review verdict

```
codex review --base origin/main
```

发现 3 个 cross-phase issue，均已 inline 修复（`1b4e4a8`）：

1. **[P1] Phase 4 follow-up** — `_settle_from_positions` 在 successful absent + HTTP error + successful absent 三步序列下仍判 LOSS（last_state 未在 error 时重置）。修：error 分支 reset last_state=None。
2. **[P2] Phase 11 follow-up** — `_aggregate_daily_journal` 没识别 trade_journal 的 per-layer 写入模式 + WIN row 已含 accumulated_loss 减项 → 多 layer cycle PnL 被双计。修：per-cycle dedup，WIN row 单独算。
3. **[P2] Phase 7 follow-up** — `_get_aiohttp_session` 缓存 short-lived loop 的 session 没回收。修：每次调用先 sweep dead-loop entries。

## 仍 owe 的 live verification（user 责任）

按 priority：

### P0 — Phase 2 server-dedup 假设（最重要）
跑 0.5 USDC + monkey-patch `client.post_order` 让首次 `time.sleep(30)` 模拟 timeout，看 polymarket.com/portfolio 实际是 1 笔还是 2 笔订单。research file `cycles/_phase2-research.md` 详细步骤。
如果 2 笔 → 起 Phase 2.1 加 reconcile-before-retry。

### P1 — Phase 1 / 4 真实数据校验
1. 跑一次 0.5 USDC 实盘买，看日志 `成交确认: limit=0.5500×10.0000 → fill=0.5420×10.0000 status=matched`，size 是 shares（10）不是 fixed-math（10000000）
2. 跨过 market 结算后，看 `单胜 (data-api redeemable=True)` 或 `单负 (data-api 仓位归零)`，对账 polymarket.com/portfolio

### P2 — Phase 3 / 5 / 9 / 11 stub-based verification
1. 双开 GUI 看锁文件 PID 保留
2. Stub `fetch_market_by_slug` 失败看 rollback flatten
3. 跑 ≥10 cycle 看 Server酱心跳推送
4. 跨过 UTC midnight 看日报生成

### P3 — Phase 7 长跑资源
`lsof -p <pid> | grep TCP | wc -l` 跑 30 分钟稳定

## 后续可能的 next step

- **PR to upstream w00c00**：仍建议等所有 live verification 跑过再 PR
- **Phase 10**：余额定时刷新（ADDENDUM 已设计）
- **Phase 12**：双策略并行（HIGH RISK，最后做）
- **Phase 2.1 重新跑 reconcile**：等 live spike 结果
