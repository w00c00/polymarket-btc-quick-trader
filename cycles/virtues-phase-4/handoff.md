# cycles/virtues-phase-4/handoff.md

> Commit `476a7b2`. Phase 4 = 反转策略实盘 WIN/LOSS 不再用 K 线颜色推断，改用 Polymarket data-api 的真实仓位 + `redeemable` 字段判定。

## 干了啥

以前 `run_reversal_live_real` 等单子"结算"那段（L1655-1681）做的是这件事：
1. 等到 trade open + 15 分钟
2. 拉 BTC 15 分钟 K 线
3. K 线收红/绿 == 期望的 win_color？是 → WIN，否 → LOSS

**问题**：BTC K 线颜色 ≠ Polymarket market 实际结算。可能 oracle 取数时刻偏一秒、可能 market 还没 resolve、可能你的仓位部分成交。这条 cycle 的 PnL、`accumulated_loss`、下一单 martingale 加注大小全部依赖这个推断 — 推断错 = 钱包失血。

修法：调 data-api `/positions`，找当前 user 拥有的 `asset == token_id` 的仓位，根据 `redeemable` 字段：
- `redeemable=True` → **WIN**（市场已结算，赢的边可兑换 1.0）
- 仓位列表里**没**这个 asset（连续两次干净 fetch 都没看到）→ **LOSS**（输的边仓位被销毁）
- 有仓位但 redeemable=False → **PENDING**，等
- 总等待时间超过 `market.end_dt + 5 分钟` 还没结论 → **PENDING_TIMEOUT**，停 cycle + Server酱 critical 推送让你去 polymarket.com/portfolio 人工核对

## Codex 找出的 V8 真问题（已 inline patch）

原 plan 让我用 `fetch_positions()` 拉数据。但 `fetch_positions` 在 HTTP 错误时**静默**返回 `[]` —— 跟"用户没仓位"看起来完全一样。两次网络抖动 = 两次 `[]` = 误判 LOSS = martingale 错方向加倍下注真金白银。

修法：加 `_fetch_positions_raw()` 跟 `fetch_positions` 同位置。Raw 版本失败时 raise；settle 函数 except 后只 sleep+retry，**不** 推进 absent-state machine。

加了 2 个回归测试：
- `test_settle_http_failure_does_not_count_as_loss`：连续 2 次 HTTP 503 + 1 次成功 → WIN（HTTP 失败不污染状态机）
- `test_settle_http_failure_then_real_absent_two_cycles`：1 次 HTTP 503 + 2 次真 absent → LOSS（只算成功的 absent）

## 你看到的差异

WIN 日志现在多了"`data-api redeemable=True`"标签，LOSS 多了"`data-api 仓位归零`"。Server 酱推送的 `结算:` 字段从 `1.0000` / `0.0000`（推断值）改成 `data-api redeemable` / `data-api 仓位归零`（真实数据源）。

新增 PENDING_TIMEOUT 路径：极少情况下 market 一直未结算或仓位状态异常，cycle 会停 + 推送一条 `⚠️ 结算异常` 告诉你去 polymarket.com/portfolio 人工看。

## 你要做的 live verification

跑一轮真实反转 cycle 让它走完 1 个 layer 的完整结算：
1. 启反转实盘，小 stake，等 trigger
2. 等单子成交后，等 market 结束
3. 看日志一行 `单胜 (data-api redeemable=True)` 或 `单负 (data-api 仓位归零)`
4. Server 酱推送对账 polymarket.com/portfolio

## 不在本 cycle 范围

- `run_reversal_live_sim` (paper) 仍用 kline_color —— 那是模拟无所谓
- `run_reversal_backtest` (回测) 同上
- Layer N 失败时已成交 layer 1..N-1 仓位 rollback → Phase 5
- timeout-then-reconcile (BLOCKER #3) → Phase 2 仍挂起
- 错误诚实呈现（POLY_1271 surface、unmatched/partial 显式分类）→ Phase 6
