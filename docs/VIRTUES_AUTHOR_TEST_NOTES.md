# Virtues Review Notes for Author Testing

This fork contains a broad pass over the Tkinter Polymarket BTC quick trader:
manual trading guardrails, reversal strategy simulation/live-trading support,
trade journaling, daily reporting, account refresh, retry handling, settlement
polling, and regression tests.

The items below intentionally exclude local account/API-credential setup issues.
They are code-level and product-level behaviors that the original author can
review or reproduce with a test account.

## Current validation

Local checks run on this branch:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m py_compile poly_mm_pro_max.py
```

Result at review time: all 117 pytest tests passed, and `py_compile` passed.

## Manual real-money trading status

Manual buy/sell flows have basic GUI guardrails:

- real-order confirmation dialogs before manual buy and manual sell;
- credential fields for private key, CLOB API credentials, funder, signature type,
  ServerChan, and MiniMax;
- logs for order book reads, best ask, submitted price/size, and exchange response;
- credential-derivation errors are surfaced instead of silently swallowed.

However, manual trading still needs clearer order-status UX before it should be
considered production-safe:

- `matched` should be described as filled;
- `live` should be described as resting/open order, not filled;
- `delayed` should be described as pending/delayed matching;
- only portfolio refresh, trade lookup, or official order status should be used
  to confirm actual fills.

## Findings to verify before live rollout

### 1. GTC orders can be treated as filled before they are actually matched

Current behavior:

- manual buy, manual sell, and live reversal buy/sell submit `OrderType.GTC`;
- `_assert_order_response_ok()` accepts `matched`, `live`, and `delayed`;
- `_extract_fill()` marks only `matched` as verified, but callers still continue
  with limit price/size when the status is `live` or `delayed`;
- the live reversal strategy records unverified buy details into
  `cycle_open_positions` and proceeds to settlement/martingale logic.

Risk:

`live` means a resting order, not a completed fill. The bot can think it owns a
position that was never filled, classify the missing position as a loss, and
advance to the next martingale layer while the original GTC order remains open
or fills later.

Suggested author test:

1. Use a small test account.
2. Submit a buy with a non-marketable limit price so the response is `live`.
3. Confirm that the GUI does not report it as filled.
4. Confirm that automated reversal logic does not advance to settlement or the
   next layer until the fill is actually verified.

Possible fixes:

- use `FOK` or `FAK` for quick buy/auto buy when the intent is immediate fill;
- treat `live` and `delayed` as "submitted but not filled";
- query order/trade status or cancel unfilled remainders before continuing;
- update GUI copy to explain `matched`/`live`/`delayed`.

### 2. Timeout retry assumes server-side deduplication that is not yet proven

Current behavior:

`_post_signed_order_with_retry()` retries the same signed order after
`asyncio.wait_for()` times out. The comment notes that server-side deduplication
is inferred, not OpenAPI-documented.

Risk:

The timed-out worker thread may still be submitting the first request. A second
post can race with the first. Depending on exchange behavior, this can produce
ambiguous order state, duplicate-order errors, or a fill after the caller already
raised an error and started rollback/reconciliation.

Suggested author test:

1. Simulate or proxy a `post_order` call that reaches the exchange but times out
   locally.
2. Verify whether re-posting the same signed order is always idempotent.
3. Verify how duplicate-order responses should be interpreted.
4. Confirm that the bot queries order/trade state before retrying or advancing.

Possible fixes:

- compute/store the order id/hash before post if available;
- after timeout, query order/trade/open-order state first;
- treat unknown order state as "manual reconciliation required";
- avoid advancing live strategy layers until the order state is resolved.

### 3. Settlement can misclassify a position as lost if it is not in the first 50 positions

Current behavior:

`_fetch_positions_raw()` calls `https://data-api.polymarket.com/positions` with
`limit=50`, sorted by current value. `_settle_from_positions()` treats two
consecutive successful responses without the target asset as `loss`.

Risk:

Accounts with many open positions or dust positions may not have the target token
in the first page. The bot can classify an unresolved/winning position as lost
and advance the martingale sequence incorrectly.

Suggested author test:

1. Mock or use an account with more than 50 positions.
2. Put the target token outside the first page.
3. Verify settlement does not return `loss` until the relevant token is searched
   across all pages or via a more targeted endpoint.

Possible fixes:

- increase limit where supported and/or paginate;
- filter by asset/market if the API supports it;
- require stronger evidence before treating missing asset as loss.

### 4. Stop button is delayed while waiting for market close after a live buy

Current behavior:

The live reversal path calls `sleep_with_stop(wait_until_close)` without passing
`self.live_auto_stop_requested`.

Risk:

After an entry is placed, pressing stop can wait until the current 15-minute
market close instead of responding promptly. The UI currently says no new order
will be placed, but the stop behavior during an open position is not explicit.

Suggested author test:

1. Start live reversal mode with a small test configuration.
2. Trigger or simulate an entry.
3. Press stop while the strategy is sleeping until market close.
4. Confirm whether it responds immediately or only after the sleep ends.

Possible fixes:

- pass the stop event into `sleep_with_stop(wait_until_close, ...)`;
- decide and document whether stop means "stop new entries only" or "begin
  rollback/flatten now";
- update GUI text accordingly.

### 5. Shared aiohttp sessions are not closed for short-lived GUI worker loops

Current behavior:

Many GUI actions create a new event loop in a worker thread and then call
`loop.close()`. Cached aiohttp sessions are keyed by loop id, but the workers do
not close sessions before closing their loops. The cache later drops stale
sessions, but that does not necessarily close connectors cleanly.

Risk:

Long GUI sessions with many scans/predictions/trades can leak network resources
or emit unclosed-session warnings.

Suggested author test:

1. Repeatedly run scan/predict/refresh actions.
2. Enable Python warnings or inspect open connections.
3. Confirm that sessions/connectors are closed when worker loops exit.

Possible fixes:

- call `_close_aiohttp_sessions()` before each worker loop closes;
- or avoid caching sessions across short-lived event loops;
- reserve shared sessions for a long-lived async runtime only.

## Suggested merge strategy

Before merging real-money features, consider splitting the PR into:

1. pure helper/tests/documentation changes;
2. manual-trading UX/status clarification;
3. live strategy changes with order-fill verification;
4. timeout/order-state reconciliation;
5. account refresh and daily-report features.

That makes it easier to validate the safety-critical trading path independently
from non-critical reporting or UI additions.
