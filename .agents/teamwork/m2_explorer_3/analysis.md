# Technical Analysis & Architectural Blueprint: Bot Execution Loop & Guardrails (Milestone 2 - Part C)

**Module**: SYNAPSE-TITAN Autonomous Bot Execution Loop, Systematic Strategy Integration & Guardrails  
**Author**: Bot Execution & Guardrails Explorer (`teamwork_explorer`)  
**Target Repository**: `C:\Users\Shivam\Desktop\trade_bot`  
**Working Directory**: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_explorer_3`  
**Date**: 2026-11-05  

---

## 1. Executive Summary & Objective

In the SYNAPSE-TITAN architecture, `LiveBotController` (`src/execution/live_bot.py`) is the central orchestrator that bridges live market feeds, quantitative forecasting pipelines, risk governance engines, and virtual order ledgers. Prior to Milestone 2, `LiveBotController` operated as a continuous un-gated loop with hardcoded default US tickers, naive conviction sorting (`abs(p - 0.50)`), fixed barrier parameters, and without any concept of a user-configured session, session duration, approved instrument basket, or allocated capital boundaries.

This blueprint specifies the production-grade re-architecture of `LiveBotController` for Milestone 2 Part C, fulfilling Requirements R2, R3, R4, and R5 from `ORIGINAL_REQUEST.md`:

1. **Session Gating**: Autonomous order generation is strictly gated by a valid `TradingSession` whose status must be `RUNNING`. Without an active session, or during `PAUSED`, `STOPPED`, or `COMPLETED` states, new orders are refused.
2. **Basket Confinement**: The bot trades strictly within the active session's approved basket (`session.instruments`), never touching unapproved symbols.
3. **Capital Boundary Enforcement**: Total capital deployed across positions is constrained strictly by `session.allocated_capital`.
4. **Dynamic Horizon Mapping**: Dynamically binds bar intervals, lookbacks, EMA spans, ATR windows, annualization factors, and Causal TCN prediction horizons via `HorizonMapper.get_parameters(session.horizon)`.
5. **Systematic Decision Engine Integration**: Replaces naive sorting with the Milestone 1 quantitative pipeline: `TradeEvaluator.evaluate()` (Net Expectancy with epistemic uncertainty and friction hurdles), `TradeRanker.rank_opportunities()` (risk-adjusted value with regime alignment and model synergy), and `PortfolioSelector.allocate()` (Fractional Kelly or HRP with the mandatory 100% Cash Allocation Guarantee).
6. **Explainable Activity Feed**: Emits human-readable plain-language explanations from `DecisionExplainer` directly to `self.activity_log` under the dedicated category `DECISION`.
7. **Session Expiry Enforcement**: Automatically calls `session_manager.check_and_enforce_expiry(self)` on every tick. When `now_utc >= session.expires_at`, triggers the configured `session_end_policy` (`CLOSE_ALL` flattens open positions; `KEEP_OPEN` preserves them for manual management) and transitions the session to `COMPLETED` without silent extension.
8. **Market Data Feed Staleness**: Enforces quote freshness against horizon-specific staleness thresholds, safely halting new entries without ever inventing synthetic prices in live market mode.
9. **Virtual Execution Isolation**: Hard-enforces `PAPER_TRADING_ONLY = True` across all pathways.

---

## 2. System Architecture & Component Interface Contracts

```
                                  ┌───────────────────────────┐
                                  │      TradingSession       │
                                  │   (SessionManager SQLite) │
                                  └─────────────┬─────────────┘
                                                │
                                    Session Config & Expiry
                                                │
                                                ▼
┌───────────────────────┐         ┌───────────────────────────┐         ┌────────────────────────┐
│  MultiAssetDataProvider│ ───────►│    LiveBotController      │◄────────┤    PaperBroker Ledger  │
│  (Genuine Quotes/Bars)│ Quotes  │   (10-Step Autonomous)    │ Orders  │ (PAPER_TRADING_ONLY)   │
└───────────────────────┘         └─────────────┬─────────────┘         └────────────────────────┘
                                                │
                                                ▼
                                  ┌───────────────────────────┐
                                  │ HorizonMapper.get_params()│
                                  │  - Intervals (5m, 1h, 1d) │
                                  │  - Annual Factor (140.2)  │
                                  │  - TCN Horizon (12 bars)  │
                                  └─────────────┬─────────────┘
                                                │
                                                ▼
                                  ┌───────────────────────────┐
                                  │   TradeEvaluator.evaluate │
                                  │  - Net Expectancy (EV > 0)│
                                  │  - Epistemic Uncertainty  │
                                  │  - Statutory Frictions    │
                                  └─────────────┬─────────────┘
                                                │
                                                ▼
                                  ┌───────────────────────────┐
                                  │ TradeRanker.rank_opps()   │
                                  │  - EV / sigma Ranking     │
                                  │  - Regime Multipliers     │
                                  │  - Crisis Hard Veto       │
                                  └─────────────┬─────────────┘
                                                │
                                                ▼
                                  ┌───────────────────────────┐
                                  │ PortfolioSelector.allocate│
                                  │  - Fractional Kelly / HRP │
                                  │  - 20% Position Cap       │
                                  │  - 100% Cash Guarantee    │
                                  └─────────────┬─────────────┘
                                                │
                                                ▼
                                  ┌───────────────────────────┐
                                  │  DecisionExplainer Logs   │
                                  │  - Category: DECISION     │
                                  │  - Plain-Language Feed    │
                                  └───────────────────────────┘
```

### 2.1 Interface Contracts

#### 1. `SessionManager` ↔ `LiveBotController`
- `bot.session_manager: Optional[SessionManager]`
- `bot.active_session_id: Optional[str]`
- `bot.get_active_session() -> Optional[TradingSession]`
- `SessionManager.check_and_enforce_expiry(bot: LiveBotController) -> Optional[TradingSession]`
  - Evaluates `session.is_expired(now_utc)`.
  - If expired: updates status to `COMPLETED`, executes `session_end_policy` (`CLOSE_ALL` or `KEEP_OPEN`), disarms bot (`is_running = False`), and returns the updated session.
- `SessionManager.start_session(session_id, bot)`:
  - Binds session parameters to bot: `bot.set_active_session(session)`.

#### 2. `HorizonMapper` ↔ `LiveBotController`
- `HorizonMapper.get_parameters(horizon: str, market_type: str = "US") -> HorizonParameters`
  - Normalized horizons: `"1 hour"`, `"1 day"`, `"1 week"`.
  - Returns `HorizonParameters` container with:
    - `bar_interval`: `"5m"`, `"1h"`, `"1d"`
    - `secondary_interval`: `"1m"`, `"15m"`, `"1h"`
    - `lookback_period`: `"5d"`, `"60d"`, `"2y"`
    - `min_bars_required`: 60, 100, 150
    - `annualization_factor`: 140.2 (1h), 40.5 (1d), 15.87 (1wk)
    - `tcn_seq_len`: 24, 30, 30
    - `tcn_horizon_bars`: 12, 7, 5
    - `pt_vol_mult`: 1.0, 1.5, 2.0
    - `sl_vol_mult`: 0.75, 1.0, 1.25
    - `quote_staleness_threshold_sec`: 60.0 (1h), 300.0 (1d), 1800.0 (1wk)

#### 3. Quantitative Decision Modules ↔ `LiveBotController`
- `TradeEvaluator.evaluate(analysis, horizon_params, min_ev_hurdle_pct, order_notional) -> TradeEvaluationResult`
- `TradeRanker.rank_opportunities(evaluations, analyses) -> List[RankedOpportunity]`
- `PortfolioSelector.allocate(ranked_opportunities, total_virtual_equity, method, current_drawdown, market_type) -> PortfolioAllocationResult`
- `DecisionExplainer`:
  - `explain_accepted_trade(opportunity, allocation, currency_symbol) -> PlainLanguageExplanation`
  - `explain_rejected_trade(opportunity, currency_symbol) -> PlainLanguageExplanation`
  - `explain_portfolio_cash_fallback(total_candidates_evaluated, rejection_summary, active_regime, current_drawdown_pct) -> PlainLanguageExplanation`

---

## 3. The 10-Step Autonomous Paper-Trading Loop Specification

The core execution method `LiveBotController.step_tick()` executes the following comprehensive 10-step sequence:

```
[Step 0: Session Gating & Expiry Enforcement]
   │
   ├─► Check session expiry: now_utc >= expires_at?
   │     └─► Trigger session_end_policy (CLOSE_ALL vs KEEP_OPEN)
   │     └─► Transition status to COMPLETED; disarm bot; return state
   │
   ├─► Session Gating check:
   │     ├─► No active session? -> Refuse execution; return state
   │     ├─► Status is PAUSED? -> Freeze new entries; allow MTM/SL
   │     └─► Status is RUNNING? -> Proceed with autonomous tick
   ▼
[Step 1: Exchange Session & Jurisdiction Hours Check]
   │  - Query MarketCalendarManager.get_session_info(ticker)
   │  - Detect transition to OPEN -> execute queued PRE_MARKET_PENDING orders
   │  - If exchange CLOSED and simulation_mode=False -> freeze price ticks strictly
   ▼
[Step 2: Genuine Market Quote Acquisition]
   │  - Query DataProvider.get_quote(ticker, market_open=True)
   │  - Record Bid, Ask, Last, Volume, Timestamp
   ▼
[Step 3: Feed Staleness & Missing Data Safeguards]
   │  - Check quote validity and age against quote_staleness_threshold_sec
   │  - If stale or unavailable: add to stale_or_invalid_tickers
   │  - Zero synthetic price generation in live market mode
   ▼
[Step 4: Working Order Evaluation & Partial Fills]
   │  - Evaluate WORKING limit orders against current Bid/Ask quotes
   │  - Fill marketable limit orders at no worse than limit_price
   ▼
[Step 5: Position Audit, Gap-Aware Stop-Loss & Conservative Intrabar SL/TP]
   │  - Update MTM unrealized P&L using realistic Bid/Ask valuation
   │  - Check stop-loss and take-profit barriers
   │  - If both SL and TP crossed in same candle: STOP_LOSS strictly takes precedence
   │  - If price gapped past stop_price: execute at worse gapped opening price
   ▼
[Step 6: Causal Prediction Pipeline Refresh]
   │  - Update SingleAssetAnalysis with live quotes
   │  - Dynamically bound to horizon intervals (5m / 1h / 1d)
   ▼
[Step 7: Basket Confinement & Candidate Opportunity Screening]
   │  - Confinement filter: ticker MUST be in active session.instruments
   │  - Tradability filter: exchange OPEN, feed fresh, no duplicate position/order
   │  - Capital boundary check: remaining_session_capital > min_notional
   ▼
[Step 8: Systematic Decision Engine: Evaluation, Ranking & Synergy]
   │  - TradeEvaluator.evaluate(): Net EV = p_cons * E[Win] - (1 - p_cons) * E[Loss] - Frictions
   │  - TradeRanker.rank_opportunities(): EV / sigma, Regime Multipliers, Crisis Veto
   ▼
[Step 9: Portfolio Allocation, 100% Cash Guarantee & Virtual Order Routing]
   │  - PortfolioSelector.allocate(): Fractional Kelly or De-noised HRP
   │  - If 0 positive EV trades: 100% Cash Allocation Guarantee enforced
   │  - If positive EV: submit orders via broker (PAPER_TRADING_ONLY = True)
   ▼
[Step 10: Telemetry, Session Metrics & Explainable Activity Feed]
   │  - Emit DecisionExplainer plain-language narratives (Category: DECISION)
   │  - Update session financial metrics in SQLite (Equity, Cash, P&L, Return)
   │  - Record Bot vs. Market comparison series and return dashboard state
```

---

## 4. Deep Dive: Implementation of the 9 Core Guardrail Requirements

### Requirement A: Session Gating
- **Objective**: Refuse execution if there is no active session or if session status is not `RUNNING`.
- **Implementation Mechanism**:
  ```python
  active_session = self.get_active_session()
  if self.session_manager is not None or self.require_session:
      if active_session is None:
          self.log_event("SESSION", "Autonomous execution halted: No active trading session configured.")
          return self.get_dashboard_state()
      if active_session.status != "RUNNING":
          if active_session.status == "PAUSED":
              # In PAUSED mode, bot suspends new trade entries but continues
              # monitoring existing open positions and executing risk stop-losses.
              allow_new_entries = False
          else:
              self.log_event("SESSION", f"Autonomous execution halted: Session #{active_session.id} is in '{active_session.status}' state.")
              return self.get_dashboard_state()
  ```
- **Guarantees**:
  - Unconfirmed setup wizard configurations cannot accidentally start trading.
  - Pausing a session immediately freezes new order submissions.
  - Terminal sessions (`COMPLETED`, `STOPPED`) permanently disarm the bot.

---

### Requirement B: Basket Confinement
- **Objective**: Never trade instruments outside the active session's approved basket.
- **Implementation Mechanism**:
  ```python
  active_session = self.get_active_session()
  if active_session is not None and active_session.instruments:
      approved_basket = set(active_session.instruments)
  else:
      approved_basket = set(self.armed_tickers)

  # Restrict candidate pool strictly to approved basket
  candidate_tickers = [tk for tk in self.armed_tickers if tk in approved_basket]
  ```
  Additionally, in the order routing pathway:
  ```python
  if active_session is not None and ticker not in approved_basket:
      self.log_event("RISK", f"Security Violation: Rejected order for {ticker} — outside approved session basket.")
      return None
  ```
- **Guarantees**:
  - Even if other tickers are loaded in `self.analyses` or `SEARCHABLE_INSTRUMENTS`, the bot strictly confines new orders to `session.instruments`.

---

### Requirement C: Capital Boundary Enforcement
- **Objective**: Ensure total allocated capital never exceeds the session's `allocated_capital`.
- **Implementation Mechanism**:
  ```python
  summary = self.broker.get_account_summary()
  available_cash = float(summary.get("available_cash", summary.get("current_cash", 0.0)))

  if active_session is not None:
      session_cap = float(active_session.allocated_capital)
      current_invested = sum(p.allocated_capital for p in still_open)
      reserved_holds = float(summary.get("reserved_cash", 0.0))
      remaining_session_capital = max(0.0, session_cap - current_invested - reserved_holds)
      deployable_capital = min(available_cash, remaining_session_capital)
  else:
      deployable_capital = available_cash

  min_trade_notional = 1000.0 if (active_session and active_session.currency == "INR") else 100.0
  if deployable_capital < min_trade_notional:
      # Boundary reached: no new positions authorized
      allow_new_entries = False
  ```
- **Guarantees**:
  - Aggregate deployed capital is hard-capped at `session.allocated_capital`.
  - Position sizing respects the 20% institutional single-stock ceiling relative to `deployable_capital`.

---

### Requirement D: Dynamic Horizon Mapping
- **Objective**: Retrieve `HorizonParameters` via `HorizonMapper.get_parameters(session.horizon)` and dynamically bind bar intervals, feature lookbacks, ATR windows, and TCN prediction horizons.
- **Implementation Mechanism**:
  ```python
  def bind_horizon_parameters(self, horizon: str, market_type: str = "US") -> HorizonParameters:
      params = HorizonMapper.get_parameters(horizon, market_type=market_type)
      self.horizon_params = params
      self.quote_staleness_threshold_sec = params.quote_staleness_threshold_sec
      self.bar_interval = params.bar_interval
      self.lookback_period = params.lookback_period
      self.log_event(
          "HORIZON",
          f"Bound Strategy Horizon '{params.horizon_name}' ({params.category}): "
          f"Bar Interval={params.bar_interval}, TCN Forward={params.tcn_horizon_bars} bars, "
          f"ATR Window={params.atr_window}, Barrier Mults=(PT: {params.pt_vol_mult}x, SL: {params.sl_vol_mult}x), "
          f"Staleness Limit={params.quote_staleness_threshold_sec:.0f}s",
          metadata=params.to_dict(),
      )
      return params
  ```
  Dynamic Barrier Sizing:
  ```python
  pt_mult = self.horizon_params.pt_vol_mult if self.horizon_params else 1.4
  sl_mult = self.horizon_params.sl_vol_mult if self.horizon_params else 1.0
  ann_factor = self.horizon_params.annualization_factor if self.horizon_params else np.sqrt(252.0)
  vol_floor = self.horizon_params.vol_floor_bar if self.horizon_params else 0.012

  vol_bar = max(r.volatility_cone.expected_vol_annualized / ann_factor, vol_floor)

  if direction == "LONG":
      pt_p = round(ref_entry_p * (1.0 + pt_mult * vol_bar), decimals)
      sl_p = round(ref_entry_p * (1.0 - sl_mult * vol_bar), decimals)
  else:
      pt_p = round(ref_entry_p * (1.0 - pt_mult * vol_bar), decimals)
      sl_p = round(ref_entry_p * (1.0 + sl_mult * vol_bar), decimals)
  ```
- **Guarantees**:
  - 1 Hour horizon uses tight 5m barriers (`1.0x / 0.75x`) and 60s staleness limits.
  - 1 Day horizon uses standard 1h barriers (`1.5x / 1.0x`) and 300s staleness limits.
  - 1 Week horizon uses wider daily swing barriers (`2.0x / 1.25x`) and 1800s staleness limits.

---

### Requirement E: Systematic Decision Engine Integration
- **Objective**: Replace naive sorting (`abs(p - 0.50)`) with `TradeEvaluator.evaluate()` + `TradeRanker.rank_opportunities()` + `PortfolioSelector.allocate()`.
- **Implementation Mechanism**:
  ```python
  # 1. Trade Evaluation with Mathematical Net Expectancy
  evaluator = TradeEvaluator(default_min_ev_hurdle_pct=0.20)
  evaluations: List[TradeEvaluationResult] = []
  analyses_map: Dict[str, SingleAssetAnalysis] = {}

  for tk in eligible_candidate_tickers:
      analysis = self.analyses[tk]
      analyses_map[tk] = analysis
      ev_result = evaluator.evaluate(
          analysis=analysis,
          horizon_params=self.horizon_params,
          order_notional=deployable_capital * 0.15,
      )
      evaluations.append(ev_result)

  # 2. Risk-Adjusted Ranking & Regime Multipliers
  ranker = TradeRanker()
  ranked_opps = ranker.rank_opportunities(
      evaluations=evaluations,
      analyses=analyses_map,
  )

  # 3. Portfolio Sizing with 100% Cash Allocation Guarantee
  selector = PortfolioSelector(
      kelly_fraction=0.30,
      target_annual_vol=0.15,
      warning_drawdown=0.08,
      max_kill_drawdown=0.15,
      max_position_cap=0.20,
      max_gross_exposure=0.95,
  )
  alloc_method = (
      active_session.strategy_config.get("allocation_method", "KELLY")
      if active_session
      else "KELLY"
  )
  market_type = active_session.market if active_session else "US"

  alloc_result = selector.allocate(
      ranked_opportunities=ranked_opps,
      total_virtual_equity=deployable_capital,
      method=alloc_method,
      current_drawdown=current_dd_dec,
      market_type=market_type,
  )
  ```
- **Guarantees**:
  - If no candidate satisfies positive Net EV after statutory frictions and uncertainty margins, `alloc_result.is_100_percent_cash` is True.
  - Sizing follows Fractional Kelly or De-noised HRP with single-position 20% capping.

---

### Requirement F: Explainable Activity Feed
- **Objective**: Emit structured plain-language explanations from `DecisionExplainer` to `self.activity_log` with category `DECISION`.
- **Implementation Mechanism**:
  ```python
  currency_sym = "₹" if (active_session and active_session.currency == "INR") else "$"

  if alloc_result.is_100_percent_cash:
      explanation = DecisionExplainer.explain_portfolio_cash_fallback(
          total_candidates_evaluated=len(ranked_opps),
          rejection_summary=alloc_result.explanation,
          current_drawdown_pct=current_dd_dec * 100.0,
      )
      self.log_event(
          "DECISION",
          f"{explanation.headline} — {explanation.summary}",
          metadata=explanation.to_dict(),
      )
  else:
      alloc_items_map = {item.ticker: item for item in alloc_result.allocations}
      for opp in ranked_opps:
          if opp.ticker in alloc_items_map:
              item = alloc_items_map[opp.ticker]
              expl = DecisionExplainer.explain_accepted_trade(
                  opportunity=opp,
                  allocation=item,
                  currency_symbol=currency_sym,
              )
              self.log_event(
                  "DECISION",
                  f"ACCEPTED {expl.headline} — {expl.summary}",
                  metadata=expl.to_dict(),
              )
          else:
              expl = DecisionExplainer.explain_rejected_trade(
                  opportunity=opp,
                  currency_symbol=currency_sym,
              )
              self.log_event(
                  "DECISION",
                  f"REJECTED {expl.headline} — {expl.summary}",
                  metadata=expl.to_dict(),
              )
  ```
- **Guarantees**:
  - Transparent audit trail of why trades were taken or rejected.
  - Emits both human-readable narrative and structured metrics in `metadata`.

---

### Requirement G: Session Expiry Enforcement
- **Objective**: On every tick, call `session_manager.check_and_enforce_expiry(self)`. When `now_utc >= session.expires_at`, trigger `session_end_policy` (`CLOSE_ALL` flattens all open positions; `KEEP_OPEN` preserves them for manual management) and transition session status to `COMPLETED` without silent extension.
- **Implementation Mechanism**:
  ```python
  if self.session_manager is not None:
      expired_session = self.session_manager.check_and_enforce_expiry(self)
      if expired_session is not None:
          self.log_event(
              "SESSION",
              f"Trading Session #{expired_session.id} expired at {expired_session.expires_at}. "
              f"Status transitioned to COMPLETED. Executed policy: '{expired_session.session_end_policy}'.",
          )
          return self.get_dashboard_state()
  ```
  Policy Execution in `SessionManager`:
  - `CLOSE_ALL`: `bot.broker.close_all_positions(bot.live_prices, reason="SESSION_EXPIRED_CLOSE_ALL")`
  - `KEEP_OPEN`: Positions remain open, pending orders cancelled.
  - Sets `bot.is_running = False` and `bot.active_session_id = None`.
- **Guarantees**:
  - Expiry is detected on the exact tick.
  - Zero silent extensions of duration.
  - Positions are cleanly flattened or safely designated for manual management.

---

### Requirement H: Market Data Feed Staleness
- **Objective**: Check quote freshness; halt new entries safely without fabricating synthetic prices if feeds are stale or unavailable.
- **Implementation Mechanism**:
  ```python
  staleness_limit = (
      self.horizon_params.quote_staleness_threshold_sec
      if self.horizon_params
      else 60.0
  )

  quote = self.data_provider.get_quote(tk, market_open=sess.is_open)
  if quote is None or not quote.is_valid:
      stale_or_invalid_tickers.add(tk)
      self.log_event(
          "FEED",
          f"Market data feed unavailable for {tk} — halting new entries (prices never fabricated).",
      )
      quotes_for_audit[tk] = prev_p
      continue

  if quote.is_stale or quote.age_seconds > staleness_limit:
      stale_or_invalid_tickers.add(tk)
      self.log_event(
          "FEED",
          f"Stale market quote for {tk} (age: {quote.age_seconds:.0f}s > limit: {staleness_limit:.0f}s) — blocking new entries.",
      )
  ```
  In live mode (`simulation_mode is False`):
  - Prices are frozen at last verified price; synthetic ticks are strictly prohibited.
  - Tickers in `stale_or_invalid_tickers` are excluded from trade evaluation.

---

### Requirement I: Virtual Execution Isolation
- **Objective**: Ensure `PAPER_TRADING_ONLY = True` is enforced across all order pathways.
- **Implementation Mechanism**:
  ```python
  from src.execution.broker import PAPER_TRADING_ONLY
  assert PAPER_TRADING_ONLY, "LiveBotController requires PAPER_TRADING_ONLY=True"

  class LiveBotController:
      def __init__(self, ...):
          assert PAPER_TRADING_ONLY, "LiveBotController requires PAPER_TRADING_ONLY=True"
          # All orders submitted exclusively through PaperBroker
          assert isinstance(self.broker, PaperBroker), "Broker must be an instance of PaperBroker"
  ```
  - Real brokerage adapters (`ZerodhaKiteAdapter`, `MT5BrokerAdapter`, `AlpacaBrokerAdapter`) raise `PermissionError` unconditionally upon order submission.
  - Dashboard telemetry and session metrics report `paper_trading_only: True`.

---

## 5. Summary Table: Guardrails & Invariants Matrix

| Guardrail Requirement | Trigger Condition | Enforcement Mechanism | Failure / Violation Behavior |
|---|---|---|---|
| **Session Gating** | No session or status != `RUNNING` | `step_tick()` gates order evaluation | Halts execution, returns dashboard state, logs `SESSION` event. |
| **Basket Confinement** | Ticker not in `session.instruments` | Filtering candidate pool & order submission check | Excluded from consideration; order rejected if attempted. |
| **Capital Boundary** | Invested + Holds >= `session.allocated_capital` | Compute `remaining_session_capital`, cap allocations | Disallows new position sizing; capital remains preserved. |
| **Dynamic Horizon** | `session.horizon` set on start | `HorizonMapper.get_parameters()` dynamic binding | Sets interval, lookback, ATR, TCN forward, and staleness limit. |
| **Systematic Engine** | Continuous during RUNNING state | Evaluator -> Ranker -> Selector pipeline | Naive sorting eliminated; trades require positive Net EV. |
| **Explainable Feed** | Trade accepted, rejected, or 100% cash | `DecisionExplainer` narrative formatting | Emits to `activity_log` with level `DECISION` and `metadata`. |
| **Session Expiry** | `now_utc >= session.expires_at` | `check_and_enforce_expiry()` on tick | Triggers `CLOSE_ALL` / `KEEP_OPEN`, transitions to `COMPLETED`. |
| **Feed Staleness** | `quote.age_seconds > threshold` or invalid | Check against `quote_staleness_threshold_sec` | Blocks new entries; never fabricates prices in live mode. |
| **Paper Isolation** | Global invariant | `assert PAPER_TRADING_ONLY` | Real-money adapters raise `PermissionError`. |

---

## 6. Next Steps & Artifact Roadmap

This specification guides the code modification and verification plan in `handoff.md`:
1. **Modifications to `src/execution/live_bot.py`**:
   - Add session management attributes and helper methods.
   - Refactor `step_tick()` with the 10-step autonomous loop integrating `TradeEvaluator`, `TradeRanker`, `PortfolioSelector`, and `DecisionExplainer`.
   - Update `get_dashboard_state()` to expose active session and horizon telemetry.
2. **Integration Test Suite**:
   - Design test specifications for `tests/test_trading_session_lifecycle.py` and `tests/test_trading_session_e2e.py`.
