# VIRTUES-PLAN-ADDENDUM.md — Phase 10/11/12 提案

> Source: 2026-05-25 对话中三个新需求按 virtues 标准的影响分析。
> 状态：**未合入 VIRTUES-PLAN.md 主体**——等 Phase 1-5 跑完再决定是否合入。
> 用途：在执行原 plan 期间作为"待考虑增量"的存档，避免遗失上下文。

---

## 三个新需求

1. **正反策略同时开** —— 三连阴转 UP 和三连阳转 DOWN 可以并行跑（当前 `live_auto_running` 是单 flag）
2. **每日交易报告** —— 每天定时生成 summary（赢输次数 / 净 PnL / 连亏序列 / 余额 diff），推送 Server酱
3. **余额定时刷新** —— 当前 `fetch_positions` 手动触发（按"刷新持仓"按钮）；改成定时（60s 一次）自动拉账户 USDC 余额 + 持仓 + 显示 stale-Xs

---

## 三个需求 × 9 条 virtues 影响矩阵

| 需求 | 紧相关 virtue | 关键风险 |
|---|---|---|
| **A. 正反策略并行** | V1 完成定义 / V3 健壮性 / V7 资源 / **V8 证明实际工作** | `live_auto_running` (poly_mm_pro_max.py:84-86) 单 flag → 升级 dict-per-mode；两边都跑 martingale 时**账户余额竞争**——一边追加加注，另一边可能资金被锁；两边胜负如果用估算 PnL 累加误差翻倍 |
| **B. 每日交易报告** | **V8 证明实际工作** / V9 可证伪沟通 / V6 测试 | 报告 PnL 是真实 fill 还是估算？若 Phase 1 未修，日报变"说漂亮话的废纸"，违反 V9 |
| **C. 余额定时刷新** | V1 完成定义 / V3 健壮性 / V7 资源 | "定时"多久（60s/5m？）；API 限流降级（保留上次值 + "stale Xs"）；长跑 24h 共 1440 次 aiohttp 调用 → 必须共享 session（依赖 Phase 7） |

---

## 依赖关系（关键发现）

**三个新需求都强依赖已有 Phase 1（真实 fill）+ Phase 4（真实结算）**。若 Phase 1/4 没修就先做这三个：

```
没修 Phase 1+4，直接做新需求 →
  A 双开    = 双倍记错 PnL（每条 cycle 误差 × 2 个策略）
  B 日报    = 报告显示假数据
  C 余额刷新 = 余额是真的，策略侧"我亏了多少"是估算的 → 两套数对账不上
```

所以这三个**必须排在 Phase 1/4 之后**。

**反向利好**：需求 C（余额刷新）解锁之前 deferred 的"日内亏损熔断 / 余额最低保护"。没有定时余额就做不了熔断。需求 C 是 prerequisite 不是单独 feature。

---

## 三个新 phase 提案

按依赖顺序追加到原 9-phase 路线之后（**不重排** 1-9，因为已经按风险优先排稳了）：

### Phase 10 — 余额 + 持仓定时刷新
**Virtue 对齐：** V1 / V3 / V7
**Goal：** 60s tick 拉 `fetch_positions` + USDC balance；UI 标 timestamp；失败降级（保留上次值 + 显示 stale Xs）
**依赖：** Phase 1（真实 fill）+ Phase 7（共享 aiohttp session）
**Tasks:**
1. 新增 `_periodic_account_refresh()` async task，60s tick；fetch USDC balance + positions
2. UI 加 timestamp 行："余额: $X.XX | 持仓: N | 上次刷新: 12s 前"
3. fetch 失败时降级：保留上次值，timestamp 颜色变橙，加 "stale" 标
**Verification:** GUI 跑 5 分钟 → UI timestamp 应每分钟+1；wifi 断开 30s → UI 显示 "stale 30s"，不 crash
**实施成本：** 中

### Phase 11 — 日内交易报告
**Virtue 对齐：** V8 / V9 / V6
**Goal：** UTC 设定时刻（默认 09:00 UTC）生成 `daily_report_YYYY-MM-DD.md` + Server酱推送
**依赖：** Phase 1（真实 fill）+ Phase 9（trade_journal.csv）+ Phase 10（余额）
**Tasks:**
1. 新增 `_generate_daily_report()` 读 trade_journal.csv 过滤当日，聚合：
   - 总 cycle 数 / WIN-LOSS 比 / 真实 PnL 累计
   - 当前余额 vs 昨日余额 diff
   - 最大连亏次数 / 当前 martingale state（如果仍开仓）
   - 异常事件计数（rollback / reconcile / timeout）
2. 跑在固定 UTC 时刻；输出 `reports/daily_report_YYYY-MM-DD.md`
3. Server酱 push 同样内容
4. pytest 覆盖：mock trade_journal.csv 多种 cycle 结果，验证聚合数字正确
**Verification:** 跑 2 天 → 收到 2 份日报；report 里 PnL 数字与 polymarket.com portfolio 当日 diff 一致
**实施成本：** 中

### Phase 12 — 正反策略并行 [HIGH RISK]
**Virtue 对齐：** V1 / V3 / V7 / **V8**
**Goal：** 两个反转策略（RED_UP + GREEN_DOWN）独立运行、独立 state、独立 stop
**依赖：** Phase 1 + 4 + 5（rollback）+ 10（实时余额做风控）
**Tasks:**
1. `live_auto_running` boolean → `dict[mode, bool]`；同理 `stop_requested` / `cycle_counter` / `live_results`
2. UI 双列：左边 RED_UP 控件，右边 GREEN_DOWN 控件，各自独立 start/stop
3. `run_reversal_live_real(mode)` 参数化；从 `live_auto_running[mode]` 读 stop 信号
4. **资金风控聚合层**：两策略叠加未平仓暴露 < `daily_max_exposure_usdc`；超出时新 cycle 直接拒绝触发
5. pytest 覆盖：两 mode 并行触发时的 state isolation；max_exposure 超限时的拒绝
**Verification:** stub 两个 mode 同时触发 → 两边 cycle 独立累计；总暴露超 cap 时第二边触发被拒并 log "max exposure reached: $XYZ > cap $ABC"
**实施成本：** **高**（碰整个 reversal_live 模块的状态模型 + UI 重设计）
**Risk note：** 这是 9 个原 phase 之后的**第一个 feature-driven 改动**（前 9 个都是 risk-driven）。引入新复杂度，必须等 Phase 1/4/5/10 全部落地后才动

---

## 跟 main plan 的衔接

| 时机 | 决策 |
|---|---|
| 现在 | 不修改 VIRTUES-PLAN.md 主体（V4 plan 稳定性 / V9 不每对话改契约） |
| Phase 1-5 跑通后 | 回头评估 Phase 10/11/12 是否仍然必要 / 优先级是否变 / 实施成本估算是否准 |
| 评估通过 | 把这三个 phase 合入 VIRTUES-PLAN.md 主体的"## Plan Overview"表格，归档本 ADDENDUM |

---

## 关于 Phase 12 的额外提醒

**Phase 12（双开）是整个路线最贵 + 最容易出 BLOCKER 的变更**：
- 状态模型重构 = 容易 regression（V1 完成定义模糊化）
- 资金竞争 = 真金白银新风险面（V3 健壮性）
- UI 重设计 = 用户行为习惯改变

实施前再做一次**专门的 Phase 12 plan 写作 + 二次 virtues 审查**，不能轻率。
