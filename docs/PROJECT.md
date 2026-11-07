# Project: SYNAPSE-TITAN Production Trading Session Wizard, Lifecycle Management & Quantitative Engine

## Architecture

The platform enhancement is engineered across four modular, production-grade synchronized milestones:

### 1. Quantitative Strategy & Opportunity Selection Engine (`src/strategy/`) [M1 - COMPLETE]
- **`UniverseSelector` (`universe_selector.py`)**: Filters market instruments based on data quality ($Q_{\text{data}} \ge 0.90$), liquidity ($ADV \ge \$5\text{M}$ USD or $\text{₹}50\text{M}$ INR), spread ($\le 25\text{ bps}$), and volatility ($8\%-100\%$). Generates bounded baskets with rationale for wizard auto-selection.
- **`TradeEvaluator` (`trade_evaluator.py`)**: Computes mathematical Net Expectancy:
  $$\text{EV} = P(\text{Win}) \cdot \mathbb{E}[\text{Win} \mid \text{Win}] - P(\text{Loss}) \cdot \mathbb{E}[\text{Loss} \mid \text{Loss}] - \text{Expected Friction Cost}$$
  Incorporates calibrated win probabilities with epistemic uncertainty lower bounds, conditional payoff barriers, gap risk buffers, and round-trip statutory/Almgren-Chriss frictions. Rejects any trade with $\text{EV} \le 0$.
- **`TradeRanker` (`trade_ranker.py`)**: Ranks candidate opportunities by risk-adjusted net value ($\text{EV} / \sigma$) and market regime alignment (State 0 Trending boost, State 1 Choppy alignment, State 2 Crisis hard veto).
- **`PortfolioSelector` (`portfolio_selector.py`)**: Allocates capital via Fractional Kelly or Marchenko-Pastur RMT de-noised HRP with single-position 20% cap. Enforces an absolute **100% Cash Allocation Guarantee** whenever zero opportunities meet positive EV hurdles or during crisis regimes.
- **`DecisionExplainer` (`decision_explainer.py`)**: Produces human-readable, transparent plain-language explanations for accepted trades, rejected trades, and 100% cash preservation.
- **`HorizonMapper` (`horizon_mapper.py`)**: Dynamically binds bar intervals, lookbacks, EMA spans, ATR windows, TCN horizons, and barrier multipliers across 1 hour (`5m`), 1 day (`1h`/`15m`), and 1 week (`1d`) horizons.
- **Capital Scaling & Market Data Guardrails**: Model predictions are strictly decoupled from account size. Position sizing scales linearly with starting capital. Real market data feed staleness halts new entries safely without fabricating synthetic prices.

### 2. Backend Architecture, Session Management & REST APIs (`server.py`, `src/execution/`) [M2 - IN PROGRESS]
- **`TradingSession` Configuration Model & Manager (`src/execution/session_manager.py`)**: Structured session entity tracking ID, market, instruments, horizon, duration, capital, currency, strategy/risk config, lifecycle state machine (`CREATED`, `RUNNING`, `PAUSED`, `COMPLETED`, `STOPPED`), timestamps, and performance metrics.
- **SQLite Database Schema Migrations (`src/execution/broker.py`)**: Idempotent migration adding `trading_sessions` table with foreign key columns (`session_id`) non-destructively added to `orders`, `positions`, `trades`, and `equity_history`.
- **FastAPI Endpoints (`server.py`)**: 11 dedicated REST endpoints for session CRUD, lifecycle actions (`start`, `pause`, `resume`, `stop`), auto-select recommendations, and performance metrics, disambiguated from physical exchange routes (`/api/sessions/status`).
- **Independent Backend Validation**: Enforces capital boundaries, currency matching (INR for Indian equities, USD for others), basket jurisdiction containment, and separation of holding horizon from run duration.
- **Execution Guardrails & Live Bot Integration (`src/execution/live_bot.py`)**: Enforces strict `PAPER_TRADING_ONLY = True`. Refuses execution without an active session. Confines trades strictly to the approved basket. Automatically triggers configured session-end policy (`CLOSE_ALL` vs `KEEP_OPEN`) upon session expiry without silent extension.

### 3. Setup Wizard UI & Bot Execution Dashboard Controls (`frontend/`) [M3]
- **`TradingSessionWizard` (`frontend/src/components/wizard/`)**: Guided 6-step onboarding wizard in React 18 / TypeScript:
  1. *Market Selection*: Supported market cards (NSE, US, Crypto, Forex, Commodities) showing trading hours, feed status, and disabling unsupported markets.
  2. *Instrument Selection*: Manual search, multi-select chips, and "Auto-select for me" powered by `UniverseSelector` with rationale.
  3. *Horizon Selection*: 1 hour, 1 day, 1 week, explicitly explaining holding horizon vs session duration.
  4. *Duration Selection*: Presets (1h, 4h, 1d, 1wk), custom duration, manual stop, and configurable session-end policy (Close open positions vs Keep open).
  5. *Virtual Capital Allocation*: Positive amount validation, boundary enforcement, and currency switching (INR `₹` vs USD `$`).
  6. *Final Confirmation Step*: Comprehensive summary review with edit options and "Confirm & Launch".
- **Session Telemetry & Dashboard Controls (`frontend/src/components/session/`)**:
  - Wizard gating blocking bot execution without confirmed session.
  - Persistent `SessionControls` (`START`, `PAUSE`, `STOP`).
  - `SessionTelemetryBar` displaying session parameters, countdown clock, financial metrics in correct currency, market regime, and feed status.
  - Upgraded `ActivityLog.tsx` with `DECISION` category displaying formatted quantitative rationales from `DecisionExplainer`.

### 4. Dual-Track Opaque-Box E2E Testing Suite & System Verification [M4]
- Comprehensive 4-tier requirement-driven opaque-box test suite (`tests/test_trading_session_e2e.py`) validating market validation, instrument selection, horizon mapping, capital sizing, session lifecycle transitions, and data outage safeguards.
- Tier 5 adversarial coverage hardening by Challenger and Forensic Integrity Audit (`teamwork_auditor`).

---

## Feature Inventory

Every feature from the Survey phase appears here with its assigned milestone:

| # | Feature | Description | Milestone | Source | Status |
|---|---------|-------------|-----------|--------|--------|
| 1 | `UniverseSelector` Module | Filter instruments by data quality, liquidity, spread, volatility; recommend bounded basket | M1 | R4, Explorer Quant | DONE |
| 2 | `TradeEvaluator` Net Expectancy | Calibrated Net Expectancy formula with uncertainty bounds, gap risk, and statutory frictions | M1 | R4, Explorer Quant | DONE |
| 3 | `TradeRanker` Opportunity Ranking | Risk-adjusted expectancy ($EV/\sigma$) and market regime alignment multipliers | M1 | R4, Explorer Quant | DONE |
| 4 | `PortfolioSelector` & Cash Fallback | Fractional Kelly/HRP capital allocation with mandatory 100% Cash fallback | M1 | R4, Explorer Quant | DONE |
| 5 | `DecisionExplainer` Explainability | Human-readable accepted/rejected and 100% cash trade explanations | M1 | R4, Explorer Quant | DONE |
| 6 | `HorizonMapper` Strategy Binding | Dynamic parameter binding across 1h, 1d, 1wk horizons | M1 | R5, Explorer Quant | DONE |
| 7 | Dynamic Capital Scaling Invariant | Linear dollar/share scaling without altering model prediction outputs | M1 | R5, Explorer Quant | DONE |
| 8 | Market Data Staleness Safeguards | Safe halting of new entries on stale/missing feeds; zero synthetic price generation | M1, M2 | R5, Explorer Quant/Backend | IN_PROGRESS |
| 9 | `TradingSession` Data Model | Structured configuration model with state machine and serialization | M2 | R3, Explorer Backend | PLANNED |
| 10 | SQLite `trading_sessions` Migration | Idempotent schema migration for session table and non-destructive foreign keys | M2 | R3, Explorer Backend | PLANNED |
| 11 | Session Lifecycle REST API Endpoints | 11 FastAPI endpoints for session CRUD, lifecycle actions, recommendations, metrics | M2 | R3, Explorer Backend | PLANNED |
| 12 | Independent Backend Validation | Robust backend validation for capital, currency, jurisdiction, and horizons | M2 | R3, Explorer Backend | PLANNED |
| 13 | Autonomous Bot Session Enforcement | Confining bot strictly to approved basket and allocated capital with active session requirement | M2 | R2, R3, Explorer Backend | PLANNED |
| 14 | Session Expiry Policy Execution | Automatic expiry check triggering configured policy (CLOSE_ALL vs KEEP_OPEN) | M2 | R2, Explorer Backend | PLANNED |
| 15 | Strict Virtual Paper Trading Isolation | Enforcing `PAPER_TRADING_ONLY = True` across all execution pathways | M2 | R2, R3, Explorer Backend | PLANNED |
| 16 | Wizard Step 1: Market Selection Card UI | Supported market cards showing hours and feed status; disabling unsupported markets | M3 | R1, Explorer Frontend | PLANNED |
| 17 | Wizard Step 2: Instrument Selection UI | Manual search, multi-select chips, and "Auto-select for me" with rationale | M3 | R1, Explorer Frontend | PLANNED |
| 18 | Wizard Step 3: Horizon Selection UI | 1h, 1d, 1wk holding horizon selection with educational explanation | M3 | R1, Explorer Frontend | PLANNED |
| 19 | Wizard Step 4: Duration & End Policy UI | Duration presets, custom, manual stop, and session-end position policy selector | M3 | R1, Explorer Frontend | PLANNED |
| 20 | Wizard Step 5: Capital Allocation UI | Positive amount validation, min/max bounds, currency switching (INR ₹ vs USD $) | M3 | R1, Explorer Frontend | PLANNED |
| 21 | Wizard Step 6: Confirmation Step UI | Summary review of all parameters with edit navigation and confirm-and-launch | M3 | R1, Explorer Frontend | PLANNED |
| 22 | Wizard Gating Layer | Autonomous paper-trading bot cannot operate until session is confirmed | M3 | R2, Explorer Frontend | PLANNED |
| 23 | Persistent Session Controls UI | Persistent START, PAUSE, STOP buttons driving session state transitions | M3 | R2, Explorer Frontend | PLANNED |
| 24 | Dashboard Session Telemetry Bar UI | Live display of active session parameters, countdown, currency metrics, regime, feed | M3 | R2, Explorer Frontend | PLANNED |
| 25 | Activity Feed Decision Explanations UI | Displaying formatted quantitative reasoning from `DecisionExplainer` in activity log | M3 | R2, Explorer Frontend | PLANNED |
| 26 | Dual-Track Opaque-Box E2E Test Suite | 4-tier comprehensive integration test suite verifying R1-R5 end-to-end | M4 | Dual Track, All | PLANNED |
| 27 | Adversarial Hardening & Forensic Audit | White-box adversarial testing (Tier 5) and strict forensic integrity audit | M4 | Dual Track, Auditor | PLANNED |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Quantitative Strategy & Horizon Mapping Engine | `src/strategy/` (`universe_selector.py`, `trade_evaluator.py`, `trade_ranker.py`, `portfolio_selector.py`, `decision_explainer.py`, `horizon_mapper.py`), unit tests in `tests/test_strategy_*.py` | None | DONE |
| M2 | Backend Architecture, Session Management & REST APIs | `src/execution/session_manager.py`, `broker.py`, `live_bot.py`, `server.py`, lifecycle tests in `tests/test_trading_session_lifecycle.py` | M1 | IN_PROGRESS |
| M3 | Setup Wizard UI & Bot Execution Dashboard Controls | `frontend/src/components/wizard/`, `session/`, `types/index.ts`, `App.tsx`, `ActivityLog.tsx`, frontend tests & build | M2 | PLANNED |
| M4 | Final E2E Integration, Adversarial Hardening & Forensic Audit | Dual-Track E2E test suite (`tests/test_trading_session_e2e.py`), Tier 5 adversarial tests, Forensic Integrity Audit | M1, M2, M3 | PLANNED |

---

## Interface Contracts

### 1. Strategy Engine ↔ Backend Execution (`src/strategy/` ↔ `src/execution/`)
- `UniverseSelector.auto_select_basket(market: str, target_size: int = 5) -> UniverseSelectionResult`
  - Returns `selected_instruments: List[str]`, `evaluations: Dict[str, CandidateEvaluation]`, `summary_rationale: str`.
- `TradeEvaluator.evaluate(analysis: SingleAssetAnalysis, horizon_params: HorizonParameters) -> TradeEvaluationResult`
  - Returns `net_expectancy_pct: float`, `is_positive_ev: bool`, `win_probability: float`, `rejection_reason: Optional[str]`.
- `TradeRanker.rank_opportunities(evaluations, regimes, analyses) -> List[RankedOpportunity]`
  - Ranks by risk-adjusted value and regime factor; vetoes crisis regimes.
- `PortfolioSelector.allocate(ranked_opportunities, total_virtual_equity, method="KELLY") -> PortfolioAllocationResult`
  - If zero positive EV trades: returns `weights={"CASH": 1.0}, cash_weight=1.0, is_100_percent_cash=True`.
- `DecisionExplainer.explain_opportunity(...) -> PlainLanguageExplanation`
  - Returns `headline: str`, `summary: str`, `factors: Dict[str, str]`, `metrics: Dict[str, Any]`.
- `HorizonMapper.get_parameters(horizon: str, market_type: str = "US") -> HorizonParameters`

### 2. Session Manager ↔ Database Ledger (`session_manager.py` ↔ `broker.py`)
- SQLite table `trading_sessions` stores complete session state.
- Foreign keys: `session_id TEXT` on `orders`, `positions`, `trades`, `equity_history`.
- `SessionManager.create_session(data) -> TradingSession`
- `SessionManager.start_session(session_id, bot) -> TradingSession`
- `SessionManager.pause_session(session_id, bot) -> TradingSession`
- `SessionManager.resume_session(session_id, bot) -> TradingSession`
- `SessionManager.stop_session(session_id, bot, reason) -> TradingSession`
- `SessionManager.check_and_enforce_expiry(bot) -> Optional[TradingSession]`

### 3. Frontend ↔ Backend REST API (`frontend/` ↔ `server.py`)
- `POST /api/sessions` — Create session with backend validation.
- `GET /api/sessions/active` — Returns current active session or `{ "session": null }`.
- `GET /api/sessions/{id}` — Fetch session details.
- `POST /api/sessions/{id}/start` — Start trading session.
- `POST /api/sessions/{id}/pause` — Pause session.
- `POST /api/sessions/{id}/resume` — Resume session.
- `POST /api/sessions/{id}/stop` — Stop session and trigger end policy.
- `POST /api/sessions/recommendations` — Auto-select recommended stock basket with rationales.
- `GET /api/sessions/{id}/performance` — Financial KPIs, P&L, trade logs.

---

## Code Layout

- Quantitative Strategy Source: `C:\Users\Shivam\Desktop\trade_bot\src\strategy\`
  - `__init__.py`
  - `horizon_mapper.py` (Horizon binding & parameters)
  - `universe_selector.py` (Screening & auto-select)
  - `trade_evaluator.py` (Net Expectancy mathematical evaluation)
  - `trade_ranker.py` (Risk-adjusted ranking & regime alignment)
  - `portfolio_selector.py` (Kelly/HRP capital allocation with 100% Cash fallback)
  - `decision_explainer.py` (Plain-language explanation generator)
- Backend Session Management & Execution: `C:\Users\Shivam\Desktop\trade_bot\src\execution\`
  - `session_manager.py` (TradingSession model, lifecycle state machine, SQLite persistence)
  - `broker.py` (Schema migrations, paper ledger, soft cash holds)
  - `live_bot.py` (Session enforcement, dynamic horizon binding, safe halting)
- Backend REST Gateway: `C:\Users\Shivam\Desktop\trade_bot\server.py`
- Frontend Source: `C:\Users\Shivam\Desktop\trade_bot\frontend\`
  - `src/types/index.ts` (Trading session, recommendation, decision types)
  - `src/components/wizard/` (6-step guided onboarding wizard)
  - `src/components/session/` (SessionControls, SessionTelemetryBar)
  - `src/components/ActivityLog.tsx` (Decision explanation category)
  - `src/App.tsx` (Session gating and integration)
- Test Suites: `C:\Users\Shivam\Desktop\trade_bot\tests\`
  - `tests/test_strategy_universe_selector.py`
  - `tests/test_strategy_trade_evaluator.py`
  - `tests/test_strategy_trade_ranker.py`
  - `tests/test_strategy_portfolio_selector.py`
  - `tests/test_strategy_horizon_mapper.py`
  - `tests/test_strategy_decision_explainer.py`
  - `tests/test_strategy_adversarial_empirical.py`
  - `tests/test_strategy_empirical_challenge.py`
  - `tests/test_trading_session_lifecycle.py`
  - `tests/test_trading_session_e2e.py`
