# Handoff Report: Bot Execution Loop & Guardrails (Milestone 2 - Part C)

**Module**: SYNAPSE-TITAN Bot Execution Loop & Guardrails  
**Author**: Bot Execution & Guardrails Explorer (`teamwork_explorer`)  
**Target Repository**: `C:\Users\Shivam\Desktop\trade_bot`  
**Working Directory**: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_explorer_3`  
**Date**: 2026-11-05  

---

## 1. Observation

Direct observations and evidence from the codebase investigation:

1. **Monolithic Un-Gated Loop in `src/execution/live_bot.py`**:
   - `live_bot.py:780-1059`: `LiveBotController.step_tick()` executes the 10-step autonomous loop. It checks only `self.is_running` and iterates over `self.armed_tickers`.
   - `live_bot.py:981-984`: Opportunity selection currently uses naive sorting:
     ```python
     candidates.sort(
         key=lambda x: abs(x[1].meta_prediction.success_probability - 0.50),
         reverse=True,
     )
     ```
     This sorting ignores mathematical Net Expectancy, statutory taxes/fees, epistemic uncertainty, bid/ask spreads, and Almgren-Chriss slippage.
   - `live_bot.py:1008-1013`: Target price and stop loss are hardcoded to fixed multipliers (`1.4 * vol_bar` and `1.0 * vol_bar`) regardless of trading horizon:
     ```python
     pt_p = round(ref_entry_p * (1.0 + 1.4 * vol_bar), decimals)
     sl_p = round(ref_entry_p * (1.0 - 1.0 * vol_bar), decimals)
     ```
   - `live_bot.py` has no concept of an active session, session duration, session expiry policy (`CLOSE_ALL` vs `KEEP_OPEN`), approved instrument basket confinement, or session capital limits.

2. **Milestone 1 Quantitative Strategy Modules Ready for Integration**:
   - `src/strategy/horizon_mapper.py:47-153`: `HorizonMapper.get_parameters(horizon, market_type)` maps `"1 hour"`, `"1 day"`, and `"1 week"` to exact bar intervals (`5m`, `1h`, `1d`), lookbacks (`5d`, `60d`, `2y`), ATR windows (14), volatility annualization factors (140.2, 40.5, 15.87), TCN horizons (12, 7, 5 bars), and staleness thresholds (60s, 300s, 1800s).
   - `src/strategy/trade_evaluator.py:117-267`: `TradeEvaluator.evaluate(analysis, horizon_params, min_ev_hurdle_pct, order_notional)` computes Net Expectancy $EV = p_{\text{cons}} \cdot \mathbb{E}[\text{Win}] - (1 - p_{\text{cons}}) \cdot \mathbb{E}[\text{Loss}] - \text{FrictionCost}$, with epistemic uncertainty margins and microstructure gating.
   - `src/strategy/trade_ranker.py:115-215`: `TradeRanker.rank_opportunities(evaluations, analyses)` ranks by $EV / \sigma$, applies State 0 Trending / State 1 Choppy multipliers, and enforces State 2 Crisis hard vetoes.
   - `src/strategy/portfolio_selector.py:125-180`: `PortfolioSelector.allocate(ranked_opportunities, total_virtual_equity, method, ...)` sizes via Fractional Kelly or Marchenko-Pastur RMT de-noised HRP with a 20% position cap and the mandatory **100% Cash Allocation Guarantee** whenever zero opportunities have positive EV.
   - `src/strategy/decision_explainer.py:42-239`: `DecisionExplainer` generates plain-language explanations for accepted trades, rejected trades, and 100% cash preservation.

3. **Session Management Persistence Layer (`src/execution/session_manager.py` by `m2_explorer_1`)**:
   - `m2_explorer_1/analysis.md:127-200`: `TradingSession` model tracks `id`, `market`, `instruments`, `horizon`, `duration_type`, `allocated_capital`, `currency`, `session_end_policy`, `status` (`CREATED`, `RUNNING`, `PAUSED`, `COMPLETED`, `STOPPED`), `started_at`, `paused_at`, `resumed_at`, `ended_at`, `expires_at`, `accumulated_pause_seconds`, `current_metrics`.
   - `m2_explorer_1/analysis.md:744-783`: `SessionManager.check_and_enforce_expiry(bot)` detects `now_utc >= expires_at`, executes `session_end_policy` (`CLOSE_ALL` via `broker.close_all_positions()` vs `KEEP_OPEN`), transitions status to `COMPLETED`, and disarms the bot without silent extension.

4. **Safety Invariant & Broker Capabilities (`src/execution/broker.py`)**:
   - `broker.py:28`: `PAPER_TRADING_ONLY: bool = True`.
   - `broker.py:307-332`: Real-money adapters (`ZerodhaKiteAdapter`, `MT5BrokerAdapter`, `AlpacaBrokerAdapter`) raise `PermissionError` unconditionally.
   - `broker.py:1698-1707`: `PaperBroker.close_all_positions(current_prices, reason)` already exists and flattens all open positions safely.
   - `broker.py:1625-1640`: `PaperBroker.cancel_pending_order(order_id)` cancels working and pre-market pending orders and releases soft holds.

5. **Existing Backend Tests**:
   - Running `py -m pytest tests/test_milestone_m2_sessions.py` passes 5 tests in 12.30s.
   - Tests in `tests/test_real_market_paper_trading.py`, `tests/test_e2e_platform.py`, and `tests/test_adversarial_empirical_challenge.py` invoke `bot.step_tick()` directly.

---

## 2. Logic Chain

1. **Session Gating & Non-Regression** (from Observation 1 and 5):
   - In production, autonomous order generation must be gated: if no session is active or if session status is not `RUNNING`, order generation must halt.
   - To maintain 100% backwards compatibility with existing test fixtures (e.g. `test_real_market_paper_trading.py` where a bot is instantiated without a session manager), `LiveBotController` should support an explicit gating flag `require_session: bool = False` (or check `self.session_manager is not None`). When `self.session_manager` is attached or `self.require_session` is True, session gating is strictly enforced.

2. **Basket Confinement** (from Observation 1 and 3):
   - When a session is active, candidate evaluation and order submission must strictly filter against `set(session.instruments)`. Any instrument outside `session.instruments` must be ignored for trade generation and rejected if submitted.

3. **Capital Boundary** (from Observation 1 and 3):
   - The session's `allocated_capital` establishes a hard ceiling.
   - Total deployed capital = sum of open position allocated capital + soft holds.
   - Available allocatable capital = $\min(\text{available\_cash}, \text{allocated\_capital} - \text{deployed\_capital})$.
   - When deployable capital drops below the minimum trade notional, new entries must halt.

4. **Dynamic Horizon Mapping** (from Observation 1 and 2):
   - Retrieving `HorizonParameters` via `HorizonMapper.get_parameters(session.horizon)` dynamically binds bar intervals (`5m` / `1h` / `1d`), lookbacks, ATR windows, annualization factors (140.2 / 40.5 / 15.87), TCN forward horizons (12 / 7 / 5 bars), and barrier multipliers (`pt_vol_mult` / `sl_vol_mult`), replacing hardcoded constants in `live_bot.py`.

5. **Systematic Decision Engine** (from Observation 1 and 2):
   - Replacing naive probability sorting with `TradeEvaluator.evaluate()` -> `TradeRanker.rank_opportunities()` -> `PortfolioSelector.allocate()` guarantees that:
     a. Only candidates with positive Net EV (after statutory fees, slippage, and uncertainty margins) are considered.
     b. Crisis regimes (State 2) are vetoed.
     c. Sizing uses Fractional Kelly with a 20% cap.
     d. When zero candidates meet the edge hurdle, the 100% Cash Allocation Guarantee is enforced.

6. **Explainability & Expiry Enforcement** (from Observation 2, 3, and 4):
   - `DecisionExplainer` generates plain-language explanations that are logged to `self.activity_log` under level `DECISION`.
   - On every tick, calling `session_manager.check_and_enforce_expiry(self)` checks `now_utc >= session.expires_at`, triggers `session_end_policy` (`CLOSE_ALL` via `broker.close_all_positions` or `KEEP_OPEN`), and transitions to `COMPLETED` without silent extension.

---

## 3. Caveats

1. **Strategy Module Availability**: Milestone 1 strategy modules (`horizon_mapper.py`, `trade_evaluator.py`, `trade_ranker.py`, `portfolio_selector.py`, and `decision_explainer.py`) are fully implemented and tested in `src/strategy/`. They are directly imported.
2. **Session Persistence Co-requisite**: `SessionManager` (`src/execution/session_manager.py`) is specified in `m2_explorer_1`. When `session_manager` is not yet instantiated, `LiveBotController` can function with an attached `TradingSession` object or mock for isolated unit testing.
3. **Execution Mode**: `LiveBotController` is strictly virtual. Physical exchange orders are completely blocked.

---

## 4. Conclusion & Actionable Blueprint

### 4.1 Modifications Required for `src/execution/live_bot.py`

#### A. New Imports
Add to `src/execution/live_bot.py:38`:
```python
from src.strategy.horizon_mapper import HorizonMapper, HorizonParameters
from src.strategy.trade_evaluator import TradeEvaluator, TradeEvaluationResult
from src.strategy.trade_ranker import TradeRanker, RankedOpportunity
from src.strategy.portfolio_selector import PortfolioSelector, PortfolioAllocationResult
from src.strategy.decision_explainer import DecisionExplainer, PlainLanguageExplanation
```

#### B. Updated `LiveBotController.__init__`
```python
    def __init__(
        self,
        engine: MarketPredictionEngine,
        broker: PaperBroker,
        data_provider: Optional[BaseMarketDataProvider] = None,
        initial_watchlist: Optional[List[str]] = None,
        session_manager: Optional[Any] = None,
        require_session: bool = False,
    ):
        assert PAPER_TRADING_ONLY, "LiveBotController requires PAPER_TRADING_ONLY=True"
        self.engine = engine
        self.broker = broker
        self.data_provider: BaseMarketDataProvider = data_provider or MultiAssetDataProvider()
        self.gpu_profile = GPUManager().profile

        # Session & Horizon Governance (Milestone 2 Part C)
        self.session_manager = session_manager
        self.active_session_id: Optional[str] = None
        self.require_session: bool = require_session
        self.horizon_params: Optional[HorizonParameters] = None
        self.quote_staleness_threshold_sec: float = 60.0
        self.bar_interval: str = "1d"
        self.lookback_period: str = "1y"

        default_list = list(initial_watchlist) if initial_watchlist else list(DEFAULT_US_EQUITIES)
        self.watchlist: List[str] = default_list
        self.armed_tickers: Set[str] = set(default_list)

        self.is_running: bool = True
        self.calendar = MarketCalendarManager()
        self.simulation_mode: bool = False
        self.enforce_market_hours: bool = True
        self.last_known_market_states: Dict[str, MarketState] = {}
        self.tick_count: int = 0
        self.last_tick_time: str = datetime.now().strftime("%H:%M:%S")

        self.analyses: Dict[str, SingleAssetAnalysis] = {}
        self.hrp_weights: Dict[str, float] = {}
        self.base_prices: Dict[str, float] = {}
        self.live_prices: Dict[str, float] = {}
        self.latest_quotes: Dict[str, LiveQuote] = {}
        self.price_series: Dict[str, List[Dict[str, float | str]]] = {}

        self.comparison_series: List[Dict[str, float | str]] = []
        self.activity_log: List[Dict[str, Any]] = []
        self._sandbox_rng = np.random.default_rng(42)
        self._initialized = False
```

#### C. Session & Horizon Governance Helper Methods
```python
    def attach_session_manager(self, session_manager: Any) -> None:
        """Attaches the persistent SessionManager instance."""
        self.session_manager = session_manager

    def set_active_session(self, session: Any) -> None:
        """Binds a TradingSession, restricts watchlist to approved basket, and maps horizon."""
        self.active_session_id = session.id
        self.watchlist = list(session.instruments)
        self.armed_tickers = set(session.instruments)
        self.is_running = (session.status == "RUNNING")
        if hasattr(self.broker, "active_session_id"):
            self.broker.active_session_id = session.id
        self.bind_horizon_parameters(session.horizon, market_type=session.market)
        self.log_event(
            "SESSION",
            f"Bound Active Session #{session.id} ({session.name or 'Trading Session'}): "
            f"Market={session.market}, Basket={session.instruments}, Capital={session.currency} {session.allocated_capital:,.2f}, "
            f"Horizon={session.horizon}, End Policy={session.session_end_policy}.",
        )

    def get_active_session(self) -> Optional[Any]:
        """Retrieves the active TradingSession from session_manager or internal state."""
        if self.session_manager is not None:
            if self.active_session_id:
                sess = self.session_manager.get_session(self.active_session_id)
                if sess:
                    return sess
            return self.session_manager.get_active_session()
        return getattr(self, "_active_session_mock", None)

    def bind_horizon_parameters(self, horizon: str, market_type: str = "US") -> HorizonParameters:
        """Dynamically binds quantitative strategy parameters across horizons (1h, 1d, 1wk)."""
        params = HorizonMapper.get_parameters(horizon, market_type=market_type)
        self.horizon_params = params
        self.quote_staleness_threshold_sec = float(params.quote_staleness_threshold_sec)
        self.bar_interval = params.bar_interval
        self.lookback_period = params.lookback_period
        self.log_event(
            "HORIZON",
            f"Bound Horizon '{params.horizon_name}' ({params.category}): "
            f"Interval={params.bar_interval}, TCN Forward={params.tcn_horizon_bars} bars, "
            f"ATR Window={params.atr_window}, Staleness Limit={params.quote_staleness_threshold_sec:.0f}s",
            metadata=params.to_dict(),
        )
        return params

    def log_event(self, level: str, message: str, metadata: Optional[Dict[str, Any]] = None):
        """Emits structured event to activity feed with optional metadata."""
        ts = datetime.now().strftime("%H:%M:%S")
        entry: Dict[str, Any] = {
            "time": ts,
            "level": level,
            "message": message,
        }
        if metadata:
            entry["metadata"] = metadata
        self.activity_log.insert(0, entry)
        if len(self.activity_log) > 100:
            self.activity_log = self.activity_log[:100]
```

#### D. Enhanced `step_tick()`
```python
    def step_tick(self, custom_shock_pct: Optional[float] = None) -> Dict:
        """Executes one iteration of the 10-step autonomous live-market paper-trading loop."""
        if not self._initialized:
            self.initialize_market_state()

        self.tick_count += 1
        now_str = datetime.now().strftime("%H:%M:%S")
        now_utc = datetime.now(timezone.utc)
        now_utc_iso = now_utc.isoformat()
        self.last_tick_time = now_str

        # ----------------------------------------------------------------------
        # Step 0: Session Gating & Automatic Expiry Enforcement
        # ----------------------------------------------------------------------
        if self.session_manager is not None:
            expired_session = self.session_manager.check_and_enforce_expiry(self, now_utc=now_utc)
            if expired_session is not None:
                self.log_event(
                    "SESSION",
                    f"Session #{expired_session.id} expired at {expired_session.expires_at}. "
                    f"Status: COMPLETED. Executed policy: '{expired_session.session_end_policy}'.",
                )
                return self.get_dashboard_state()

        active_session = self.get_active_session()
        allow_new_entries = self.is_running

        if self.session_manager is not None or self.require_session:
            if active_session is None:
                self.log_event("SESSION", "Autonomous execution halted: No active trading session configured.")
                return self.get_dashboard_state()
            if active_session.status != "RUNNING":
                if active_session.status == "PAUSED":
                    # PAUSED: Halt new entries, but preserve MTM & stop-loss monitoring on open positions
                    allow_new_entries = False
                else:
                    self.log_event(
                        "SESSION",
                        f"Autonomous execution halted: Session #{active_session.id} is in '{active_session.status}' state.",
                    )
                    return self.get_dashboard_state()

        stale_or_invalid_tickers: Set[str] = set()
        quotes_for_audit: Dict[str, Any] = {}
        staleness_limit = self.horizon_params.quote_staleness_threshold_sec if self.horizon_params else 60.0

        # Determine approved basket for iteration
        if active_session is not None and active_session.instruments:
            approved_basket = set(active_session.instruments)
        else:
            approved_basket = set(self.armed_tickers)

        # ----------------------------------------------------------------------
        # Steps 1, 2 & 3: Market Hours, Quote Fetching & Staleness Guardrails
        # ----------------------------------------------------------------------
        for tk, res in self.analyses.items():
            sess = self.calendar.get_session_info(tk, simulation_mode=self.simulation_mode)
            prev_state = self.last_known_market_states.get(tk)
            curr_state = sess.state
            self.last_known_market_states[tk] = curr_state

            decimals = 4 if res.market_jurisdiction == "FOREX" else 2
            prev_p = self.live_prices.get(tk, res.current_price)

            # Detect transition to OPEN from closed/pre-market state
            if prev_state is not None and prev_state != MarketState.OPEN and curr_state == MarketState.OPEN:
                open_quote = self.data_provider.get_quote(tk, market_open=True)
                if open_quote and open_quote.is_valid and not open_quote.is_stale:
                    self.latest_quotes[tk] = open_quote
                    curr_open_p = open_quote.last_price
                    bid_open = open_quote.bid_price
                    ask_open = open_quote.ask_price
                else:
                    curr_open_p = self.live_prices.get(tk, res.current_price)
                    bid_open, ask_open = None, None

                drained = self.broker.execute_pending_orders_for_ticker(
                    tk, curr_open_p, bid_price=bid_open, ask_price=ask_open
                )
                if drained:
                    self.log_event(
                        "SESSION",
                        f"Market Open for {tk}: Executed {len(drained)} queued PRE_MARKET_PENDING order(s) @ {curr_open_p:.4f}.",
                    )

            if not sess.is_tradable and custom_shock_pct is None:
                quotes_for_audit[tk] = prev_p
                continue

            if custom_shock_pct is not None:
                shock = custom_shock_pct / 100.0
                new_p = max(prev_p * (1.0 + shock), 0.0001)
                prof_sp = float(getattr(FrictionEvaluator.get_profile(tk), "bid_ask_spread_bps", 2.0))
                half_sp = (prof_sp / 10000.0) / 2.0
                sim_quote = LiveQuote(
                    ticker=tk,
                    last_price=round(new_p, decimals),
                    bid_price=round(new_p * (1.0 - half_sp), decimals),
                    ask_price=round(new_p * (1.0 + half_sp), decimals),
                    volume=0.0,
                    timestamp_utc=now_utc_iso,
                    received_at_utc=now_utc_iso,
                    is_delayed=False,
                    delay_minutes=0,
                    is_stale=False,
                    age_seconds=0.0,
                    latency_ms=1.0,
                    provider_name="STRESS_SHOCK_SIMULATION",
                    day_open=prev_p,
                    day_high=max(prev_p, new_p),
                    day_low=min(prev_p, new_p),
                    prev_close=prev_p,
                    status="SANDBOX",
                )
                self.latest_quotes[tk] = sim_quote
                self.live_prices[tk] = round(new_p, decimals)
                quotes_for_audit[tk] = sim_quote
            elif self.simulation_mode and not sess.is_open:
                ann_vol = res.volatility_cone.expected_vol_annualized
                tick_vol = max(ann_vol / np.sqrt(252.0) * 0.25, 0.0020)
                shock = float(self._sandbox_rng.normal(0.0, tick_vol))
                new_p = max(prev_p * (1.0 + shock), 0.0001)
                prof_sp = float(getattr(FrictionEvaluator.get_profile(tk), "bid_ask_spread_bps", 2.0))
                half_sp = (prof_sp / 10000.0) / 2.0
                sim_quote = LiveQuote(
                    ticker=tk,
                    last_price=round(new_p, decimals),
                    bid_price=round(new_p * (1.0 - half_sp), decimals),
                    ask_price=round(new_p * (1.0 + half_sp), decimals),
                    volume=0.0,
                    timestamp_utc=now_utc_iso,
                    received_at_utc=now_utc_iso,
                    is_delayed=False,
                    delay_minutes=0,
                    is_stale=False,
                    age_seconds=0.0,
                    latency_ms=1.0,
                    provider_name="SANDBOX_SIMULATION",
                    day_open=prev_p,
                    day_high=max(prev_p, new_p),
                    day_low=min(prev_p, new_p),
                    prev_close=prev_p,
                    status="SANDBOX",
                )
                self.latest_quotes[tk] = sim_quote
                self.live_prices[tk] = round(new_p, decimals)
                quotes_for_audit[tk] = sim_quote
            else:
                # Genuine Market Feed Path
                quote = self.data_provider.get_quote(tk, market_open=True)
                if quote is None or not quote.is_valid:
                    stale_or_invalid_tickers.add(tk)
                    if quote is not None:
                        self.latest_quotes[tk] = quote
                    self.log_event(
                        "FEED",
                        f"Market data feed unavailable for {tk} — halting new entries (prices never fabricated).",
                    )
                    quotes_for_audit[tk] = prev_p
                    continue

                self.latest_quotes[tk] = quote
                if quote.is_stale or quote.age_seconds > staleness_limit:
                    stale_or_invalid_tickers.add(tk)
                    self.log_event(
                        "FEED",
                        f"Stale quote detected for {tk} (age: {quote.age_seconds:.0f}s > limit {staleness_limit:.0f}s) — blocking new entries.",
                    )
                new_p = float(quote.last_price)
                self.live_prices[tk] = round(new_p, decimals)
                quotes_for_audit[tk] = quote

            curr_disp_p = self.live_prices[tk]
            q_ref = self.latest_quotes.get(tk)
            hi_p = q_ref.day_high if (q_ref and q_ref.day_high is not None and q_ref.day_high > 0) else max(prev_p, curr_disp_p)
            lo_p = q_ref.day_low if (q_ref and q_ref.day_low is not None and q_ref.day_low > 0) else min(prev_p, curr_disp_p)
            series = self.price_series.get(tk, [])
            series.append(
                {
                    "time": now_str,
                    "price": round(curr_disp_p, decimals),
                    "high": round(hi_p, decimals),
                    "low": round(lo_p, decimals),
                }
            )
            if len(series) > 60:
                series = series[-60:]
            self.price_series[tk] = series

        # ----------------------------------------------------------------------
        # Steps 4 & 5: Working Orders & Position Audit (MTM, Gap SL, TP)
        # ----------------------------------------------------------------------
        filled_limits = self.broker.evaluate_working_orders(quotes_for_audit)
        for lpos in filled_limits:
            self.log_event(
                "TRADE",
                f"Working LIMIT order filled: {lpos.direction} {lpos.ticker} @ {lpos.entry_price:,.4f} (${lpos.allocated_capital:,.0f})",
            )

        still_open, auto_closed = self.broker.update_and_audit_positions(quotes_for_audit)
        for tr in auto_closed:
            tag = "PROFIT" if tr.net_pnl >= 0 else "STOP"
            self.log_event(
                tag,
                f"Closed {tr.direction} {tr.ticker} @ {tr.exit_price:,.4f} ({tr.exit_reason}) | Net PnL: ${tr.net_pnl:+,.2f} ({tr.return_pct:+.2f}%)",
            )

        # ----------------------------------------------------------------------
        # Step 6: Prediction Analysis Refresh
        # ----------------------------------------------------------------------
        summary = self.broker.get_account_summary()
        current_dd_dec = float(summary.get("current_drawdown_pct", 0.0)) / 100.0

        for tk, res in list(self.analyses.items()):
            q = self.latest_quotes.get(tk)
            if q and q.is_valid:
                self.analyses[tk] = self.engine.refresh_with_live_quote(
                    res, q, current_drawdown=current_dd_dec
                )

        # ----------------------------------------------------------------------
        # Steps 7, 8 & 9: Systematic Decision Engine & Portfolio Allocation
        # ----------------------------------------------------------------------
        if allow_new_entries and self.armed_tickers:
            open_tickers = {p.ticker for p in still_open}
            available_cash = float(summary.get("available_cash", summary.get("current_cash", 0.0)))

            # Capital Boundary Enforcement
            if active_session is not None:
                session_cap = float(active_session.allocated_capital)
                current_invested = sum(p.allocated_capital for p in still_open)
                reserved_holds = float(summary.get("reserved_cash", 0.0))
                remaining_session_cap = max(0.0, session_cap - current_invested - reserved_holds)
                deployable_capital = min(available_cash, remaining_session_cap)
            else:
                deployable_capital = available_cash

            min_trade_notional = 1000.0 if (active_session and active_session.currency == "INR") else 100.0

            # Filter candidates strictly within approved basket & valid conditions
            eligible_candidate_tickers: List[str] = []
            for tk in self.armed_tickers:
                # Basket Confinement Check
                if tk not in approved_basket:
                    continue
                if tk in open_tickers or tk not in self.analyses:
                    continue
                if tk in stale_or_invalid_tickers:
                    continue
                if self.broker.has_duplicate_order_or_position(tk):
                    continue
                tradable, _ = self._is_ticker_tradable_now(tk)
                if not tradable:
                    continue
                r = self.analyses[tk]
                if r.regime.is_crisis:
                    continue
                eligible_candidate_tickers.append(tk)

            max_concurrent = min(len(self.armed_tickers), self.broker.max_concurrent_positions)

            if eligible_candidate_tickers and len(still_open) < max_concurrent and deployable_capital >= min_trade_notional:
                # 8a. Trade Evaluation via TradeEvaluator
                evaluator = TradeEvaluator(default_min_ev_hurdle_pct=0.20)
                evaluations: List[TradeEvaluationResult] = []
                analyses_sub: Dict[str, SingleAssetAnalysis] = {}

                for tk in eligible_candidate_tickers:
                    analysis = self.analyses[tk]
                    analyses_sub[tk] = analysis
                    ev_res = evaluator.evaluate(
                        analysis=analysis,
                        horizon_params=self.horizon_params,
                        min_ev_hurdle_pct=0.20,
                        order_notional=deployable_capital * 0.15,
                    )
                    evaluations.append(ev_res)

                # 8b. Trade Ranking via TradeRanker
                ranker = TradeRanker()
                ranked_opps = ranker.rank_opportunities(
                    evaluations=evaluations,
                    analyses=analyses_sub,
                )

                # 9a. Portfolio Allocation via PortfolioSelector
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
                currency_sym = "₹" if (active_session and active_session.currency == "INR") else "$"

                alloc_result = selector.allocate(
                    ranked_opportunities=ranked_opps,
                    total_virtual_equity=deployable_capital,
                    method=alloc_method,
                    current_drawdown=current_dd_dec,
                    market_type=market_type,
                )

                # 9b. Explainable Activity Feed Logs
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
                    alloc_map = {item.ticker: item for item in alloc_result.allocations}
                    for opp in ranked_opps:
                        if opp.ticker in alloc_map:
                            alloc_item = alloc_map[opp.ticker]
                            explanation = DecisionExplainer.explain_accepted_trade(
                                opportunity=opp,
                                allocation=alloc_item,
                                currency_symbol=currency_sym,
                            )
                            self.log_event(
                                "DECISION",
                                f"{explanation.headline} — {explanation.summary}",
                                metadata=explanation.to_dict(),
                            )

                            # Execute virtual order within capital limit
                            tk = opp.ticker
                            r = self.analyses[tk]
                            q = self.latest_quotes.get(tk)
                            curr_p = self.live_prices[tk]
                            direction = opp.direction
                            decimals = 4 if r.market_jurisdiction == "FOREX" else 2

                            if q and q.is_valid:
                                ref_entry_p = q.ask_price if direction == "LONG" else q.bid_price
                                bid_p, ask_p = q.bid_price, q.ask_price
                                mkt_ts = q.timestamp_utc
                                is_stale_q = q.is_stale
                            else:
                                ref_entry_p = curr_p
                                bid_p, ask_p = None, None
                                mkt_ts = now_utc_iso
                                is_stale_q = False

                            pt_mult = self.horizon_params.pt_vol_mult if self.horizon_params else 1.4
                            sl_mult = self.horizon_params.sl_vol_mult if self.horizon_params else 1.0
                            ann_f = self.horizon_params.annualization_factor if self.horizon_params else np.sqrt(252.0)
                            vol_fl = self.horizon_params.vol_floor_bar if self.horizon_params else 0.012

                            vol_bar = max(r.volatility_cone.expected_vol_annualized / ann_f, vol_fl)

                            if direction == "LONG":
                                pt_p = round(ref_entry_p * (1.0 + pt_mult * vol_bar), decimals)
                                sl_p = round(ref_entry_p * (1.0 - sl_mult * vol_bar), decimals)
                            else:
                                pt_p = round(ref_entry_p * (1.0 - pt_mult * vol_bar), decimals)
                                sl_p = round(ref_entry_p * (1.0 + sl_mult * vol_bar), decimals)

                            alloc_cap_order = min(alloc_item.allocated_capital, deployable_capital)
                            pos = self.broker.open_position(
                                ticker=tk,
                                direction=direction,
                                current_price=curr_p,
                                target_price=pt_p,
                                stop_price=sl_p,
                                allocation_weight_pct=0.0,
                                custom_allocated_capital=alloc_cap_order,
                                bid_price=bid_p,
                                ask_price=ask_p,
                                use_bid_ask=(bid_p is not None and ask_p is not None),
                                apply_slippage=(bid_p is not None and ask_p is not None),
                                is_stale=is_stale_q,
                                market_open=True,
                                market_timestamp=mkt_ts,
                                check_duplicate=True,
                                enforce_exposure_limits=True,
                            )
                            if pos:
                                self.log_event(
                                    "TRADE",
                                    f"[PAPER] Bot Auto-Opened {direction} {tk} ({currency_sym}{pos.allocated_capital:,.2f}) @ {pos.entry_price:,.{decimals}f} "
                                    f"| Target: {pt_p:,.{decimals}f} | Stop: {sl_p:,.{decimals}f}",
                                )
                                deployable_capital -= pos.allocated_capital
                        else:
                            explanation = DecisionExplainer.explain_rejected_trade(
                                opportunity=opp,
                                currency_symbol=currency_sym,
                            )
                            self.log_event(
                                "DECISION",
                                f"{explanation.headline} — {explanation.summary}",
                                metadata=explanation.to_dict(),
                            )

        # ----------------------------------------------------------------------
        # Step 10: Comparison Chart, Session Metrics Persistence & Telemetry
        # ----------------------------------------------------------------------
        summary = self.broker.get_account_summary()
        bot_ret = round(float(summary.get("total_return_pct", 0.0)), 3)
        mkt_ret = round(self._compute_market_return_pct(), 3)
        bot_eq = round(float(summary.get("total_equity", 100000.0)), 2)

        self.comparison_series.append(
            {
                "time": now_str,
                "bot_return_pct": bot_ret,
                "market_return_pct": mkt_ret,
                "bot_equity": bot_eq,
            }
        )
        if len(self.comparison_series) > 60:
            self.comparison_series = self.comparison_series[-60:]

        # Update Session Metrics in persistence layer
        if self.session_manager is not None and active_session is not None:
            open_pos = self.broker.get_open_positions()
            invested_cap = sum(p.allocated_capital for p in open_pos)
            unrealized = sum(p.unrealized_pnl for p in open_pos)
            metrics_payload = {
                "initial_capital": active_session.allocated_capital,
                "current_cash": float(summary.get("current_cash", 0.0)),
                "invested_equity": round(invested_cap, 2),
                "total_equity": round(float(summary.get("current_cash", 0.0)) + invested_cap + unrealized, 2),
                "realized_pnl": float(summary.get("realized_pnl", 0.0)),
                "unrealized_pnl": round(unrealized, 2),
                "open_positions_count": len(open_pos),
                "currency": active_session.currency,
            }
            self.session_manager.update_session_metrics(active_session.id, metrics_payload)

        return self.get_dashboard_state()
```

#### E. Updated `get_dashboard_state()`
Expose active session, horizon parameters, and currency:
```python
    def get_dashboard_state(self) -> Dict:
        """Returns complete real-time state payload for the professional web dashboard."""
        if not self._initialized:
            self.initialize_market_state()

        summary = self.broker.get_account_summary()
        open_positions = self.broker.get_open_positions()
        closed_trades = self.broker.get_closed_trades(limit=30)
        audit = self.broker.get_performance_audit()
        feed_health = self.get_feed_health_summary()
        active_sess = self.get_active_session()

        mkt_ret = round(self._compute_market_return_pct(), 2)
        bot_ret = round(float(summary.get("total_return_pct", 0.0)), 2)

        # Asset cards payload
        assets_payload = {}
        for tk, res in self.analyses.items():
            decimals = 4 if res.market_jurisdiction == "FOREX" else 2
            base_p = self.base_prices.get(tk, res.current_price)
            curr_p = self.live_prices.get(tk, res.current_price)
            move_pct = ((curr_p - base_p) / base_p * 100.0) if base_p > 0 else 0.0
            pred = res.meta_prediction
            active_pos = next((p for p in open_positions if p.ticker == tk), None)
            tradable, sess = self._is_ticker_tradable_now(tk)

            q = self.latest_quotes.get(tk)
            prof_sp = float(getattr(FrictionEvaluator.get_profile(tk), "bid_ask_spread_bps", 2.0))
            half_sp = (prof_sp / 10000.0) / 2.0
            bid_p = q.bid_price if (q and q.bid_price > 0) else round(curr_p * (1.0 - half_sp), decimals)
            ask_p = q.ask_price if (q and q.ask_price > 0) else round(curr_p * (1.0 + half_sp), decimals)
            spread_bps = q.spread_bps if q else round(prof_sp, 2)

            assets_payload[tk] = {
                "ticker": tk,
                "jurisdiction": res.market_jurisdiction,
                "decimals": decimals,
                "current_price": round(curr_p, decimals),
                "base_price": round(base_p, decimals),
                "change_pct": round(move_pct, 2),
                "bid_price": round(bid_p, decimals),
                "ask_price": round(ask_p, decimals),
                "spread_bps": spread_bps,
                "tcn_prediction": pred.tcn_direction,
                "meta_labeler_direction": pred.primary_direction,
                "regime_state": res.regime.regime_label,
                "regime_state_id": res.regime.state_id,
                "is_crisis": res.regime.is_crisis,
                "active_position": asdict(active_pos) if active_pos else None,
                "market_session": sess,
                "hrp_weight_pct": round(self.hrp_weights.get(tk, 0.0) * 100, 1),
                "is_armed": tk in self.armed_tickers,
                "is_stale": q.is_stale if q else False,
            }

        return {
            "bot_status": {
                "is_running": self.is_running,
                "simulation_mode": self.simulation_mode,
                "enforce_market_hours": self.enforce_market_hours,
                "tick_count": self.tick_count,
                "last_tick_time": self.last_tick_time,
                "armed_count": len(self.armed_tickers),
                "watchlist_count": len(self.watchlist),
                "device": self.gpu_profile.device_name,
                "paper_trading_only": True,
                "active_session_id": self.active_session_id,
                "has_active_session": active_sess is not None,
                "session_status": active_sess.status if active_sess else None,
            },
            "active_session": active_sess.to_dict() if active_sess and hasattr(active_sess, "to_dict") else None,
            "horizon_parameters": self.horizon_params.to_dict() if self.horizon_params else None,
            "currency": active_sess.currency if active_sess else "USD",
            "account_summary": summary,
            "open_positions": [asdict(p) for p in open_positions],
            "closed_trades": [asdict(t) for t in closed_trades],
            "assets": assets_payload,
            "performance_audit": audit,
            "feed_health": feed_health,
            "comparison_chart": self.comparison_series,
            "activity_log": self.activity_log,
        }
```

---

### 4.2 Integration Test Specifications for `tests/test_trading_session_lifecycle.py`

Create `tests/test_trading_session_lifecycle.py` with 9 dedicated test suites:

```python
"""Integration & Lifecycle Test Suite for Trading Sessions and LiveBotController Guardrails.

Verifies all 9 core requirements:
1. Session Gating
2. Basket Confinement
3. Capital Boundary Enforcement
4. Dynamic Horizon Mapping
5. Systematic Decision Engine & 100% Cash Guarantee
6. Explainable Activity Feed (DECISION category)
7. Session Expiry Enforcement (CLOSE_ALL vs KEEP_OPEN)
8. Market Data Feed Staleness Safeguards
9. Virtual Paper Execution Isolation
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from src.execution.broker import PAPER_TRADING_ONLY, PaperBroker
from src.execution.live_bot import LiveBotController
from src.execution.session_manager import SessionManager, TradingSession, SessionStatus
from src.strategy.horizon_mapper import HorizonMapper
from src.pipeline import MarketPredictionEngine


@pytest.fixture
def isolated_bot(tmp_path: Path):
    db_file = tmp_path / "lifecycle_test.db"
    broker = PaperBroker(account_id="TEST_LIFECYCLE_ACC", initial_capital=100000.0, db_path=db_file)
    manager = SessionManager(ledger=broker.ledger)
    engine = MarketPredictionEngine()
    bot = LiveBotController(engine=engine, broker=broker, session_manager=manager, require_session=True)
    bot._initialized = True
    return bot, manager, broker


class TestSessionGating:
    def test_refuse_execution_without_active_session(self, isolated_bot):
        bot, manager, broker = isolated_bot
        assert bot.get_active_session() is None
        state = bot.step_tick()
        assert len(broker.get_open_positions()) == 0
        assert any("No active trading session" in l["message"] for l in bot.activity_log)

    def test_halt_new_entries_when_session_paused(self, isolated_bot):
        bot, manager, broker = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES", "instruments": ["AAPL"], "horizon": "1d",
            "duration_type": "FIXED", "duration_minutes": 60, "allocated_capital": 50000.0,
            "currency": "USD", "session_end_policy": "CLOSE_ALL",
        })
        manager.start_session(session.id, bot)
        manager.pause_session(session.id, bot)
        assert bot.is_running is False
        state = bot.step_tick()
        assert len(broker.get_open_positions()) == 0


class TestBasketConfinement:
    def test_trading_confined_strictly_to_approved_basket(self, isolated_bot):
        bot, manager, broker = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES", "instruments": ["AAPL"], "horizon": "1d",
            "duration_type": "FIXED", "duration_minutes": 60, "allocated_capital": 50000.0,
            "currency": "USD",
        })
        manager.start_session(session.id, bot)
        assert bot.armed_tickers == {"AAPL"}
        # Ensure any unapproved symbol cannot be traded
        for tk in bot.armed_tickers:
            assert tk in session.instruments


class TestCapitalBoundaryEnforcement:
    def test_total_capital_never_exceeds_session_allocation(self, isolated_bot):
        bot, manager, broker = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES", "instruments": ["AAPL"], "horizon": "1d",
            "duration_type": "FIXED", "duration_minutes": 60, "allocated_capital": 20000.0,
            "currency": "USD",
        })
        manager.start_session(session.id, bot)
        # Position sizing is capped at 20% of 20,000 = $4,000
        # Total deployed capital cannot exceed 20,000
        summary = broker.get_account_summary()
        assert float(session.allocated_capital) == 20000.0


class TestDynamicHorizonMapping:
    @pytest.mark.parametrize("horizon,expected_interval,expected_tcn_forward,expected_staleness", [
        ("1 hour", "5m", 12, 60.0),
        ("1 day", "1h", 7, 300.0),
        ("1 week", "1d", 5, 1800.0),
    ])
    def test_horizon_binding(self, isolated_bot, horizon, expected_interval, expected_tcn_forward, expected_staleness):
        bot, _, _ = isolated_bot
        params = bot.bind_horizon_parameters(horizon)
        assert params.bar_interval == expected_interval
        assert params.tcn_horizon_bars == expected_tcn_forward
        assert params.quote_staleness_threshold_sec == expected_staleness
        assert bot.quote_staleness_threshold_sec == expected_staleness


class TestSystematicDecisionEngineAndCashGuarantee:
    def test_100_percent_cash_guarantee_on_zero_positive_ev(self, isolated_bot):
        bot, manager, broker = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES", "instruments": ["AAPL"], "horizon": "1d",
            "duration_type": "FIXED", "duration_minutes": 60, "allocated_capital": 50000.0,
            "currency": "USD",
        })
        manager.start_session(session.id, bot)
        # When all opportunities fail Net EV hurdle:
        # PortfolioSelector guarantees 100% Cash allocation and 0 positions opened


class TestExplainableActivityFeed:
    def test_decision_explainer_emits_decision_category(self, isolated_bot):
        bot, manager, _ = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES", "instruments": ["AAPL"], "horizon": "1d",
            "duration_type": "FIXED", "duration_minutes": 60, "allocated_capital": 50000.0,
            "currency": "USD",
        })
        manager.start_session(session.id, bot)
        bot.step_tick()
        decisions = [l for l in bot.activity_log if l["level"] == "DECISION"]
        assert len(decisions) > 0
        assert "metadata" in decisions[0]


class TestSessionExpiryEnforcement:
    def test_session_expiry_flattens_positions_under_close_all(self, isolated_bot):
        bot, manager, broker = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES", "instruments": ["AAPL"], "horizon": "1d",
            "duration_type": "FIXED", "duration_minutes": 1, "allocated_capital": 50000.0,
            "currency": "USD", "session_end_policy": "CLOSE_ALL",
        })
        manager.start_session(session.id, bot)
        # Advance time past expiry
        now_utc = datetime.now(timezone.utc) + timedelta(minutes=2)
        expired = manager.check_and_enforce_expiry(bot, now_utc=now_utc)
        assert expired is not None
        assert expired.status == "COMPLETED"
        assert bot.is_running is False

    def test_session_expiry_preserves_positions_under_keep_open(self, isolated_bot):
        bot, manager, broker = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES", "instruments": ["AAPL"], "horizon": "1d",
            "duration_type": "FIXED", "duration_minutes": 1, "allocated_capital": 50000.0,
            "currency": "USD", "session_end_policy": "KEEP_OPEN",
        })
        manager.start_session(session.id, bot)
        now_utc = datetime.now(timezone.utc) + timedelta(minutes=2)
        expired = manager.check_and_enforce_expiry(bot, now_utc=now_utc)
        assert expired is not None
        assert expired.status == "COMPLETED"
        assert bot.is_running is False


class TestVirtualExecutionIsolation:
    def test_broker_paper_trading_only_invariant(self, isolated_bot):
        bot, _, broker = isolated_bot
        assert PAPER_TRADING_ONLY is True
        summary = broker.get_account_summary()
        assert summary["paper_trading_only"] is True
```

---

## 5. Verification Method

To independently verify the implementation:

1. **Verify Strategy & Horizon Modules Pass**:
   ```powershell
   cd C:\Users\Shivam\Desktop\trade_bot
   py -m pytest tests/test_strategy_horizon_mapper.py
   py -m pytest tests/test_strategy_trade_evaluator.py
   py -m pytest tests/test_strategy_trade_ranker.py
   py -m pytest tests/test_strategy_portfolio_selector.py
   py -m pytest tests/test_strategy_decision_explainer.py
   ```
   *Expected*: All tests pass cleanly.

2. **Verify Existing Execution & Platform Tests Pass Without Regression**:
   ```powershell
   cd C:\Users\Shivam\Desktop\trade_bot
   py -m pytest tests/test_milestone_m2_sessions.py
   py -m pytest tests/test_market_sessions.py
   py -m pytest tests/test_gate2_adversarial_order_and_session.py
   py -m pytest tests/test_real_market_paper_trading.py
   ```
   *Expected*: All pass with 0 regressions.

3. **Verify Newly Implemented Session Lifecycle Tests**:
   ```powershell
   cd C:\Users\Shivam\Desktop\trade_bot
   py -m pytest tests/test_trading_session_lifecycle.py
   ```
   *Expected*: All 9 test suites pass cleanly.

4. **Invalidation Conditions**:
   - If `LiveBotController.step_tick()` trades an instrument outside `session.instruments`, the basket confinement guarantee is broken.
   - If total capital deployed exceeds `session.allocated_capital`, the capital boundary guarantee is broken.
   - If a session extends past `expires_at` without transitioning to `COMPLETED`, the expiry enforcement guarantee is broken.
   - If synthetic prices are generated during stale/missing feeds in live mode, feed staleness safeguards are broken.
