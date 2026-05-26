# cycles/virtues-phase-5/handoff.md

> Commit `2ebc0a5`. Phase 5 = 反转 cycle 中途任何 abort 都先 flatten 已成交的仓位 + 用 data-api 探测当前 layer 是否有 orphan（覆盖 Phase 2 retry-post 异常 race）。

## 干了啥

之前 `run_reversal_live_real` 的 layer loop 有 4 个退出路径会留 orphan 仓位：
1. market lookup 失败 → `break`，前面 layer 仓位丢
2. `ask > entry_price` → `break`，同上
3. `buy_quick_market` 抛异常 → 整个 worker 死，仓位丢
4. `outcome == "pending_timeout"` → `return`，**当层**和前面 layer 仓位都丢

Phase 5 改：
- 维护 `cycle_open_positions: list[dict]` 跟踪本 cycle 已成交 layer
- 加 `_flatten_cycle_positions(open_positions, reason, cycle_count)` async helper：每个 position 读 best_bid_ask，按 `max(bid*0.95, tick)` 卖出（V8 floor 防 thin book），最后 push 一条 Server酱 `⚠️ 周期回滚` summary
- 4 个 abort 路径都先 flatten 再退
- layer body 包 `try/except Exception` —— 异常时 flatten + re-raise

## Codex 找的 V3 真 blocker（已 inline 修）

原 plan：`cycle_open_positions.append(...)` 是在 `buy_quick_market` 成功 return 之后。**但 Phase 2 的 retry-post RuntimeError 是在订单可能已被 exchange 接受的情况下抛的**——这种 case 异常 path 看不到当前 layer 的仓位，flatten 只能搞前面 layer，**当前 layer 留 orphan**。

修法：outer `except Exception` 加 probe：
```python
pending_token_id = locals().get("token_id")
if pending_token_id and not any(p["layer"] == layer for p in cycle_open_positions):
    probe_positions = await self._fetch_positions_raw()
    probe_match = next((p for p in probe_positions if p.get("asset") == pending_token_id), None)
    if probe_match and float(probe_match.get("size")) > 0.000001:
        cycle_open_positions.append({...with data-api fill_size...})
        log.warning("layer N 异常时仓位仍在 size=X，加入回滚")
```

如果 exchange 真接受了订单，data-api 在几秒内会显示这个 position，probe 能抓到它的真 size + avgPrice 然后 flatten。如果 exchange 没接受，probe 找不到，自然跳过。

`_fetch_positions_raw`（Phase 4 加的）失败时 raise（不像 `fetch_positions` 静默返回 []），所以 probe 错误也有 log。

## 你看到的差异

正常 cycle 行为不变（WIN/LOSS 仍按 Phase 4 真实仓位判定）。

异常 cycle 时多收一条：
```
[ERROR] 反转实盘 layer 2 异常中断: <exception>
[WARNING] layer 2 异常时仓位仍在 size=18.7430，加入回滚   ← 新（如果 probe 命中）
[WARNING] rollback layer 1 卖出: size=10.0000 price=0.3800 resp=...
[WARNING] rollback layer 2 卖出: size=18.7430 price=0.4500 resp=...
```

Server 酱 critical push：
```
### ⚠️ 反转实盘周期中断回滚

- 周期: 3
- 原因: layer_exception:RuntimeError:post_order 重试 2 次仍超时...
- 回滚结果:
- layer 1: OK 0.3800 x 10.0000
- layer 2: OK 0.4500 x 18.7430

请去 polymarket.com/portfolio 人工对账。
```

## 你要做的 live verification

**Stub 1（rollback 基础路径）**：monkeypatch `fetch_market_by_slug` 返回 None on 2nd layer call。0.5 USDC stake。期望：layer 1 成交 → layer 2 market 找不到 → 自动 flatten layer 1 → polymarket.com/portfolio 看 layer 1 已平仓或挂卖单。

**Stub 2（buy-exception probe）**：monkeypatch `_post_signed_order_with_retry` 让它先放一个真订单到 exchange，然后 raise RuntimeError。期望：layer 异常 → probe 查 data-api → 命中 → flatten 当前 layer。

两个 stub 都跑成功 = Phase 5 完整落地。

## 已知遗留（按 Codex warn）

- **Integration tests 缺**：5 个单测覆盖 `_flatten_cycle_positions` 本体，但**没**覆盖 4 个 abort call site 跟 layer 循环的 integration。这是 V6 gap，但 mock `run_reversal_live_real` 需要 Tk + async + 8+ deps，太复杂。Live spike 替代单测覆盖
- **Phase 2 race 仍在 sell 路径**：`sell_token_limit` 通过 Phase 2 的 `_post_signed_order_with_retry`，**理论上**被 Phase 2 的 server-dedup 假设保护，但仍 inherit 同样的 "evidence-based, not OpenAPI-documented" 状态
- **try/except 不抓 KeyboardInterrupt/SystemExit**：Ctrl-C 时仍可能 orphan。Tk shutdown hook 是 Phase 12 / 跨平台 phase 的事
