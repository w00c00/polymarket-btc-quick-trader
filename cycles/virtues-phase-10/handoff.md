# cycles/virtues-phase-10/handoff.md

> Commit `abbeb36`. Phase 10（ADDENDUM）= 60s 自动刷新账户：USDC 余额 + 仓位市值 + 持仓数。失败 90s 后 label 变橙色。

## 干了啥

GUI 持仓表上方加一条状态 label：

```
余额: $42.18 | 持仓市值: $25.30 | 持仓: 3 条 | 刷新: 4s 前
```

每 60 秒自动刷新一次，并发拉 3 个数据源：

1. **持仓表** —— 已有 `fetch_positions()` 路径
2. **持仓市值** —— **data-api /value**（官方文档已 verify，2026-05-26）。返回的是仓位 size × curPrice 求和，**不是**钱包 USDC
3. **钱包 USDC** —— **Polygon JSON-RPC eth_call(USDC.balanceOf(funder))**，因为 data-api 没暴露 wallet balance

钱包余额走链上 RPC（`polygon-rpc.com` 公共 endpoint，免 key）：
```
USDC contract: 0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174 (Polygon USDC.e)
ERC20 balanceOf selector: 0x70a08231
USDC 6 decimals → hex_int / 1e6
```

90s 没成功刷新 → label 变橙色 `刷新: 95s 前`，**旧数字保留**（不要显示假数据）。

## Codex 抓的 V3 真 blocker（已 inline 修）

原 `_apply_account_refresh` 不管 fetch 成不成功都 `account_last_refresh_ts = now`。意思是网络全挂时，next tick 看到 ts 是新的 → label 不变橙色 → 用户以为数据是最新的，实际几分钟前的。

修法：用 `pos_value` 和 `balance` 的 `None vs not-None` 作为信号（`fetch_positions` 静默返回 `[]` 太模糊，可能是 HTTP 错也可能是真没仓位）。只在至少一个 explicit 源成功才 advance ts。

加 2 个测试：
- `test_apply_refresh_preserves_ts_when_all_sources_fail`
- `test_apply_refresh_advances_ts_when_balance_succeeds`

## 你看到的差异

GUI 持仓表上方多一行 label。每 60s 数字滚动。网断 90s 后橙色 stale 标记。其他功能不变。

## 你要做的 live verification

1. 启 GUI → 3 秒后 label 出现，显示真实数字
2. polymarket.com → Cash 看 USDC 余额，跟 GUI label `$X.XX` 对账
3. polymarket.com/portfolio 看持仓总值，跟 `$Y.YY` 对账
4. 拔网 90 秒 → label 应变橙色，数字保留
5. 接网 → 60s 内变回灰色

## 不在本 phase scope

- ❌ 日内亏损熔断 / 余额最低保护（"账户余额 < $X 自动停反转策略"）—— Phase 10 只做数据基础设施
- ❌ Phase 12 双开（HIGH RISK，需 Phase 1/4/5 live-verify 前置）

## 整体路线图状态

Phase 10 land 之后：
- 主体 9 + Phase 11 + final-patches + Phase 10 = **11 个 cycle 全部 land 进 main**
- Phase 12 仍 deferred（plan draft 在 `cycles/_phase12-plan-draft.md`，HIGH RISK 警告 + pre-condition list）
- 117 pytest cases

下一可能动作：
- 你跑全套 live verification（Phase 1 / 2 / 4 / 5 / 10 各自的"user owes"步骤）
- 通过后再决定要不要起 Phase 12
- 或者 PR 给上游 w00c00
