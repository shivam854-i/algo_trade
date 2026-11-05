# Backend Architecture Survey & Technical Blueprint (R2 & R3)
**SYNAPSE-TITAN Autonomous Paper-Trading Platform**
*Author: Backend Architecture Explorer (`teamwork_explorer`)*
*Date: 2026-11-05*
*Target Path: `C:\Users\Shivam\Desktop\trade_bot`*

---

## 1. Executive Summary

This report delivers a deep investigation of the existing backend architecture in `C:\Users\Shivam\Desktop\trade_bot`, establishes the foundational blueprint for **R2 (Autonomous Bot Behavior, Session Lifecycle, and UI Dashboard Controls)** and **R3 (Backend Architecture, Session Management, and REST APIs)**, and details the integration points with the quantitative decision engine (R4) and strategy horizon mapping (R5).

### Key Architectural Findings:
1. **FastAPI & Uvicorn Runtime**: `server.py` hosts the REST API with asynchronous lifespan initialization, hosting singletons for `MarketPredictionEngine`, `BacktestEngine`, `PaperBroker`, and `LiveBotController`.
2. **SQLite Trading Ledger**: `data/trading_ledger.db` (managed by `TradingLedgerDB` in `src/execution/broker.py`) stores virtual accounts, positions, orders, trades, and equity history using an idempotent, non-destructive migration pattern (`CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN` inside exception guards).
3. **Physical Market Session Timings**: `src/execution/market_sessions.py` enforces real-world exchange calendars (NSE Mumbai, NYSE/NASDAQ, CME Globex, Forex, Crypto 24/7), 6-state state machines (`OPEN`, `PRE_MARKET`, `POST_MARKET`, `CLOSED`, `WEEKEND`, `HOLIDAY`), and second-precision countdowns.
4. **Data Ingestion & Routing**: `src/data/provider_base.py` implements a composite `MultiAssetDataProvider` that routes US Equities to `AlpacaProvider` (when credentials are present) and falls back to `YFinanceProvider` with explicit delay and staleness telemetry (`age_seconds`, `is_stale`, `is_delayed`).
5. **Permanent Paper-Trading Lock**: Real-money brokerage execution is permanently locked out via `PAPER_TRADING_ONLY = True` across `broker.py` and `live_bot.py`.
6. **Gap Identified for R2 & R3**: The current backend manages physical market sessions (`/api/sessions/status`) and armed watchlist tickers, but lacks a formal **User-Controlled TradingSession** lifecycle model, persistent session state table, session-scoped capital/instrument boundaries, independent backend validation, and lifecycle controls (`CREATE`, `START`, `PAUSE`, `RESUME`, `STOP`).

---

## 2. Existing Backend Architecture Analysis

### 2.1 File-by-File Technical Inspection

#### 2.1.1 `server.py` (FastAPI Application)
- **Lifespan Manager** (`lifespan(app: FastAPI)`):
  - Initializes `MarketPredictionEngine()` and `BacktestEngine()`.
  - Instantiates `LiveBotController(engine, broker=broker_engine)`.
  - Warmed up via `live_bot.initialize_market_state()`.
- **Existing Endpoints**:
  - `GET /` — Serves static / Vite frontend build (`frontend/dist/index.html`).
  - `GET /api/health` — System health, PyTorch GPU acceleration status, CUDA VRAM.
  - `GET /api/universes` — Pre-configured asset lists (`US_TECH`, `INDIAN_EQUITIES`, etc.).
  - `GET /api/forecast/{ticker}` — Single-asset prediction, volatility cone, regime.
  - `POST /api/scan` — Multi-asset batch scan and HRP portfolio weight calculation.
  - `POST /api/backtest` — Walk-forward backtest simulation with statutory friction.
  - `GET /api/broker/account`, `GET /api/broker/positions`, `GET /api/broker/trades` — Account summary, open positions, trade history.
  - `GET /api/dashboard/state` — Aggregated real-time bot status, comparison series, asset telemetry.
  - `GET /api/feed/health` — Data feed health, latency, provider name, staleness.
  - `GET /api/sessions/status` — Physical market session status for `NSE_INDIA`, `US_MARKETS`, `CME_GLOBEX`, `CRYPTO_247`. *(Note: Must remain backward-compatible!)*
  - `GET /api/dashboard/orders/pending`, `DELETE /api/dashboard/orders/cancel/{order_id}` — Pre-market queue and cancellation.
  - `POST /api/dashboard/order`, `POST /api/dashboard/bot-trade` — Manual and AI-assisted order submission.
  - `POST /api/dashboard/toggle` — Starts / pauses `live_bot.is_running`.
  - `POST /api/dashboard/step` — Manual tick step for testing/simulation.
  - `POST /api/dashboard/flatten`, `POST /api/dashboard/reset` — Liquidate positions, reset account.
- **Architectural Observations**:
  - Routes currently mutate global `live_bot` and `broker_engine`.
  - Orders are submitted against account `'PAPER_DEFAULT'`.
  - There is no concept of a session ID in the order/position models.

#### 2.1.2 `src/execution/broker.py` (Execution & SQLite Ledger)
- **`TradingLedgerDB`**:
  - Database file: `data/trading_ledger.db`.
  - Tables: `accounts`, `positions`, `trades`, `orders`, `equity_history`, `users`.
  - Migration Pattern: All migrations are handled in `_init_db()` using `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ... ADD COLUMN ...` inside `try...except` blocks.
- **`PaperBroker`**:
  - Operates strictly with virtual capital.
  - Enforces soft cash holds for queued pre-market orders (`status = 'PRE_MARKET_PENDING'`), reserving cash in `reserved_cash` without deducting `current_cash` until filled.
  - Dynamic spread & slippage via `compute_realistic_fill_price` using `FrictionEvaluator` (Almgren-Chriss market impact model).
  - Methods: `open_position`, `close_position`, `close_all_positions`, `queue_pre_market_order`, `cancel_pending_order`, `execute_pending_orders_for_ticker`, `evaluate_working_orders`, `update_and_audit_positions`, `reset_account`.

#### 2.1.3 `src/execution/live_bot.py` (`LiveBotController`)
- **10-Step Autonomous Loop (`step_tick`)**:
  1. Checks physical exchange session status (`MarketCalendarManager`).
  2. Fetches genuine market quotes (`data_provider.get_quote`).
  3. Validates quote freshness and missing-data guardrails (never invents prices).
  4. Evaluates working limit orders and audits open positions.
  5. Enforces gap-aware stop-loss and conservative intrabar take-profit.
  6. Refreshes point-in-time prediction pipeline.
  7. Evaluates HMM regime and multi-tiered risk guardrails.
  8. Computes CVaR-Kelly & HRP position sizes.
  9. Submits virtual paper orders with bid/ask spreads + Almgren-Chriss slippage.
  10. Persists state to SQLite and records comparison series (`bot_return_pct` vs `market_return_pct`).
- **Key State Variables**:
  - `self.watchlist`: List of symbols loaded into memory.
  - `self.armed_tickers`: Set of symbols the bot is actively permitted to trade.
  - `self.is_running`: Boolean flag controlling automated trading.
  - `self.simulation_mode`: Toggles strict real-world market hours vs. 24/7 sandbox override.

#### 2.1.4 `src/execution/market_sessions.py`
- Implements `MarketCalendarManager` with precise statutory holiday schedules (NSE 2026/2027 and NYSE 2026/2027).
- Calculates exact second-by-second countdowns to next market open/close boundaries.
- Detects jurisdiction: `NSE_CASH`, `US_EQUITIES`, `COMMODITY`, `CRYPTO`, `FOREX`.
- Automatic Daylight Saving Time (DST) handling: EDT (UTC-4) in summer vs. EST (UTC-5) in winter.

#### 2.1.5 `src/data/provider_base.py`
- Abstract `BaseMarketDataProvider` with standardized `LiveQuote` (contains `is_stale`, `age_seconds`, `latency_ms`, `is_delayed`, `status`).
- Concrete providers: `AlpacaProvider`, `YFinanceProvider`, `ZerodhaKiteProvider`, `CCXTWebSocketProvider`, `MultiAssetDataProvider`.
- `DataProviderRegistry`: Dynamic factory registration.

### 2.2 Existing Test Infrastructure & Health
- Test runner: Python 3.13.7 on Windows using `py -m pytest`.
- Existing test suites:
  - `tests/test_market_sessions.py`: **35 passed** (100% pass rate).
  - `tests/test_milestone_m2_sessions.py`: **5 passed** (100% pass rate).
  - `tests/test_e2e_platform.py`: **42 passed** (100% pass rate).
  - `tests/test_gate2_adversarial_order_and_session.py`: **10 passed, 1 minor float rounding assert** (0.01000003 delta on cash hold).
  - Frontend: `npm test` runs vitest: **22 passed** across 4 test files (100% pass rate).

---

## 3. Requirements R2 & R3 Architectural Blueprint

### 3.1 Data Model: `TradingSession`
A robust, production-grade session configuration must capture the complete operational contract defined in the Setup Wizard.

```
+-------------------------------------------------------------------------------------------------------+
|                                          TRADING SESSION MODEL                                        |
+-------------------------------------------------------------------------------------------------------+
| Field Name                | Type      | Nullable | Constraints / Description                          |
+---------------------------+-----------+----------+----------------------------------------------------+
| session_id                | TEXT (PK) | NO       | UUID4 format (e.g., 'sess_20261105_7a2e84')        |
| user_id                   | TEXT      | NO       | Scoped user identifier (default: 'DEFAULT_USER')   |
| account_id                | TEXT      | NO       | Virtual ledger account (e.g., 'PAPER_DEFAULT')     |
| name                      | TEXT      | YES      | Human-readable session name                        |
| market                    | TEXT      | NO       | 'US_EQUITIES' | 'INDIAN_NSE' | 'CRYPTO' |          |
|                           |           |          | 'FOREX' | 'COMMODITIES'                            |
| instruments               | TEXT      | NO       | JSON array of approved tickers: ["NVDA", "AAPL"]   |
| horizon                   | TEXT      | NO       | Trading holding horizon: '1h' | '1d' | '1wk'       |
| duration_type             | TEXT      | NO       | 'PRESET' | 'CUSTOM' | 'MANUAL'                     |
| duration_minutes          | INTEGER   | YES      | Run duration in minutes (NULL if MANUAL)           |
| session_end_policy        | TEXT      | NO       | 'CLOSE_ALL' | 'KEEP_OPEN' (default: 'CLOSE_ALL')   |
| allocated_capital         | REAL      | NO       | Positive float > 0.0                               |
| currency                  | TEXT      | NO       | 'USD' (US, Crypto, FX, Comm) or 'INR' (NSE)        |
| strategy_config           | TEXT      | NO       | JSON blob: bar_interval, feature_window, barriers   |
| risk_config               | TEXT      | NO       | JSON blob: kelly_fraction, max_pos_pct, max_dd_pct  |
| status                    | TEXT      | NO       | 'CREATED' | 'RUNNING' | 'PAUSED' | 'COMPLETED' |   |
|                           |           |          | 'STOPPED' | 'HALTED_SAFETY'                        |
| created_at                | TEXT      | NO       | ISO 8601 UTC timestamp                             |
| started_at                | TEXT      | YES      | ISO 8601 UTC timestamp of initial launch           |
| paused_at                 | TEXT      | YES      | ISO 8601 UTC timestamp of most recent pause        |
| resumed_at                | TEXT      | YES      | ISO 8601 UTC timestamp of most recent resume       |
| ended_at                  | TEXT      | YES      | ISO 8601 UTC timestamp when completed/stopped      |
| expires_at                | TEXT      | YES      | ISO 8601 UTC calculated expiration boundary        |
| accumulated_pause_seconds | INTEGER   | NO       | Total seconds spent paused (prevents early expiry) |
| current_metrics           | TEXT      | YES      | JSON blob: financial KPIs, P&L, drawdown           |
| last_heartbeat_at         | TEXT      | YES      | ISO 8601 UTC timestamp of last bot evaluation tick |
+---------------------------+-----------+----------+----------------------------------------------------+
```

#### Detailed JSON Blob Specifications:

**`strategy_config` Schema:**
```json
{
  "horizon": "1h",
  "bar_interval": "15m",
  "feature_window_bars": 60,
  "tcn_lookback_bars": 30,
  "regime_lookback_bars": 120,
  "triple_barrier_pt_mult": 1.4,
  "triple_barrier_sl_mult": 1.0,
  "min_signal_conviction": 0.55,
  "allow_shorting": true
}
```

**`risk_config` Schema:**
```json
{
  "kelly_fraction": 0.35,
  "max_position_weight_pct": 20.0,
  "max_portfolio_exposure_pct": 80.0,
  "max_drawdown_limit_pct": 10.0,
  "max_concurrent_positions": 5,
  "cvar_tail_risk_filter": true,
  "allow_sit_in_cash": true
}
```

**`current_metrics` Schema:**
```json
{
  "starting_capital": 50000.0,
  "current_cash": 38500.0,
  "invested_equity": 12150.0,
  "total_equity": 50650.0,
  "unrealized_pnl": 650.0,
  "realized_pnl": 0.0,
  "total_return_pct": 1.30,
  "max_drawdown_pct": 0.45,
  "active_positions_count": 2,
  "closed_trades_count": 0,
  "win_rate_pct": 0.0,
  "friction_paid": 14.25
}
```

---

### 3.2 Database Schema Migration Plan (SQLite)

To ensure zero risk of database corruption and seamless migration for existing test environments:

1. **`trading_sessions` Table Creation**:
   Execute inside `TradingLedgerDB._init_db()`:
   ```sql
   CREATE TABLE IF NOT EXISTS trading_sessions (
       id TEXT PRIMARY KEY,
       user_id TEXT NOT NULL DEFAULT 'DEFAULT_USER',
       account_id TEXT NOT NULL DEFAULT 'PAPER_DEFAULT',
       name TEXT,
       market TEXT NOT NULL,
       instruments TEXT NOT NULL,
       horizon TEXT NOT NULL,
       duration_type TEXT NOT NULL,
       duration_minutes INTEGER,
       session_end_policy TEXT NOT NULL DEFAULT 'CLOSE_ALL',
       allocated_capital REAL NOT NULL,
       currency TEXT NOT NULL DEFAULT 'USD',
       strategy_config TEXT NOT NULL,
       risk_config TEXT NOT NULL,
       status TEXT NOT NULL DEFAULT 'CREATED',
       created_at TEXT NOT NULL,
       started_at TEXT,
       paused_at TEXT,
       resumed_at TEXT,
       ended_at TEXT,
       expires_at TEXT,
       accumulated_pause_seconds INTEGER DEFAULT 0,
       current_metrics TEXT,
       last_heartbeat_at TEXT
   );

   CREATE INDEX IF NOT EXISTS idx_sessions_status ON trading_sessions(status);
   CREATE INDEX IF NOT EXISTS idx_sessions_market ON trading_sessions(market);
   CREATE INDEX IF NOT EXISTS idx_sessions_account ON trading_sessions(account_id);
   ```

2. **Non-Destructive Column Alterations to Existing Tables**:
   Add `session_id TEXT` to `orders`, `positions`, `trades`, and `equity_history` inside `try...except` blocks:
   ```sql
   ALTER TABLE orders ADD COLUMN session_id TEXT;
   ALTER TABLE positions ADD COLUMN session_id TEXT;
   ALTER TABLE trades ADD COLUMN session_id TEXT;
   ALTER TABLE equity_history ADD COLUMN session_id TEXT;
   ```
   Followed by index creation:
   ```sql
   CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(session_id);
   CREATE INDEX IF NOT EXISTS idx_positions_session ON positions(session_id);
   CREATE INDEX IF NOT EXISTS idx_trades_session ON trades(session_id);
   ```

3. **Guarantees**:
   - Idempotent: Can run repeatedly without errors.
   - Non-blocking: SQLite schema alterations are instant.
   - Backward Compatible: Existing tests and rows with `session_id = NULL` remain 100% valid.

---

### 3.3 FastAPI REST API Specification

The REST API endpoints will be added to `server.py` (or partitioned cleanly into `src/execution/session_manager.py` + router).

#### 3.3.1 Critical Route Namespace Disambiguation
Notice: `server.py` already exposes `GET /api/sessions/status` for physical market exchange status.
To maintain absolute backward compatibility, `/api/sessions/status` must be preserved, while new session routes are mapped explicitly:
- Specific static routes (`/api/sessions/active`, `/api/sessions/recommendations`, `/api/sessions/status`) are registered **before** parameterized routes (`/api/sessions/{session_id}`).

#### 3.3.2 Endpoint Signatures & Specifications

| Method | Endpoint | Description | Request Body | Response Status |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/sessions` | Create a new trading session | `SessionCreateRequest` | `201 Created` |
| `GET` | `/api/sessions/active` | Get current active session (or null) | None | `200 OK` |
| `GET` | `/api/sessions/{session_id}` | Fetch session details and metrics | None | `200 OK` |
| `GET` | `/api/sessions` | List sessions (with status/market filter) | Query params (`status`, `market`, `limit`) | `200 OK` |
| `PUT` | `/api/sessions/{session_id}` | Update parameters (only if `CREATED`/`PAUSED`) | `SessionUpdateRequest` | `200 OK` |
| `POST` | `/api/sessions/{session_id}/start` | Start session execution | None | `200 OK` |
| `POST` | `/api/sessions/{session_id}/pause` | Pause active session | None | `200 OK` |
| `POST` | `/api/sessions/{session_id}/resume` | Resume paused session | None | `200 OK` |
| `POST` | `/api/sessions/{session_id}/stop` | Stop session & trigger end policy | `SessionStopRequest` (optional) | `200 OK` |
| `POST` | `/api/sessions/recommendations` | Get auto-select stock recommendations | `RecommendationRequest` | `200 OK` |
| `GET` | `/api/sessions/{session_id}/performance`| Get detailed performance metrics & audit | None | `200 OK` |

#### 3.3.3 Detailed Pydantic Request & Response Schemas

```python
class SessionCreateRequest(BaseModel):
    name: Optional[str] = Field(None, description="Session name")
    market: str = Field(..., description="US_EQUITIES, INDIAN_NSE, CRYPTO, FOREX, COMMODITIES")
    instruments: List[str] = Field(..., min_items=1, max_items=20, description="Approved basket of tickers")
    horizon: str = Field(..., description="Trading holding horizon: 1h, 1d, 1wk")
    duration_type: str = Field(default="PRESET", description="PRESET, CUSTOM, MANUAL")
    duration_minutes: Optional[int] = Field(None, ge=15, le=43200, description="Session runtime in minutes")
    session_end_policy: str = Field(default="CLOSE_ALL", description="CLOSE_ALL or KEEP_OPEN")
    allocated_capital: float = Field(..., gt=0.0, description="Virtual capital allocated")
    currency: str = Field(default="USD", description="Currency code (USD or INR)")
    strategy_overrides: Optional[Dict[str, Any]] = None
    risk_overrides: Optional[Dict[str, Any]] = None

class SessionUpdateRequest(BaseModel):
    name: Optional[str] = None
    instruments: Optional[List[str]] = None
    session_end_policy: Optional[str] = None
    duration_minutes: Optional[int] = None

class RecommendationRequest(BaseModel):
    market: str = Field(..., description="Target market")
    horizon: str = Field(default="1d", description="1h, 1d, 1wk")
    capital: float = Field(default=10000.0, gt=0.0)
    risk_tolerance: str = Field(default="MODERATE", description="CONSERVATIVE, MODERATE, AGGRESSIVE")
    max_recommendations: int = Field(default=5, ge=1, le=10)

class RecommendationItem(BaseModel):
    ticker: str
    name: str
    sector: str
    current_price: float
    currency: str
    expected_net_value: float
    win_probability: float
    signal: str
    recommended_allocation_pct: float
    rationale: str
    data_quality_score: float
    liquidity_score: float

class RecommendationResponse(BaseModel):
    market: str
    horizon: str
    total_evaluated: int
    recommendations: List[RecommendationItem]
    selection_summary: str
```

---

### 3.4 Independent Backend Validation Logic

Validation must execute on the backend regardless of frontend state:

1. **Capital & Currency Rules**:
   - `allocated_capital > 0.0` and finite.
   - Minimum capital:
     - `INDIAN_NSE`: Minimum ₹25,000 INR; Maximum ₹50,000,000 INR.
     - `US_EQUITIES`: Minimum $500 USD; Maximum $1,000,000 USD.
     - `CRYPTO` / `FOREX` / `COMMODITIES`: Minimum $500 USD.
   - Currency match validation:
     - If `market == "INDIAN_NSE"`, `currency` MUST be `"INR"`.
     - If `market in ("US_EQUITIES", "CRYPTO", "FOREX", "COMMODITIES")`, `currency` MUST be `"USD"`.
     - *Rejection on mismatch*: Return HTTP 422 with message: `"Currency mismatch: Market INDIAN_NSE requires currency INR, got USD."`

2. **Market & Instrument Basket Consistency**:
   - Basket cannot be empty (`1 <= len(instruments) <= 20`).
   - Every ticker in `instruments` must belong to the selected market:
     - Use `MarketCalendarManager.detect_market_type(ticker)`:
       - `INDIAN_NSE` -> ticker must detect as `NSE_CASH` (e.g., `.NS` or `.BO` suffix).
       - `US_EQUITIES` -> ticker must detect as `US_EQUITIES`.
       - `COMMODITIES` -> ticker must detect as `COMMODITY`.
       - `CRYPTO` -> ticker must detect as `CRYPTO`.
       - `FOREX` -> ticker must detect as `FOREX`.
     - *Rejection on foreign asset*: Return HTTP 422 with message: `"Instrument AAPL does not belong to market INDIAN_NSE."`
   - Instrument symbols must be sanitized (trimmed and uppercased).

3. **Trading Horizon vs. Session Duration Separation**:
   - `horizon` defines analytical resolution and trade holding period:
     - `"1h"`: Short-term momentum, 15m/1h bars, tighter 1.2x/0.8x barriers.
     - `"1d"`: Standard swing, 1d bars, 1.4x/1.0x barriers.
     - `"1wk"`: Position trend, 1d/1wk bars, 2.0x/1.5x barriers.
   - `duration_type` & `duration_minutes` define when the bot terminates:
     - If `duration_type == "MANUAL"`, `duration_minutes` is `None` (bot runs until user clicks STOP).
     - If `duration_type in ("PRESET", "CUSTOM")`, `duration_minutes` must be between 15 and 43,200 (30 days).

4. **Session-End Policy**:
   - Must be strictly one of `{"CLOSE_ALL", "KEEP_OPEN"}`.

---

### 3.5 Execution Guardrails & Safety Invariants

1. **Virtual Paper Trading Strict Isolation**:
   - Real-money brokerage execution is permanently forbidden.
   - Attempting to pass live credentials or non-paper account results in HTTP 403 Forbidden.
2. **Refusal of Execution Without Active Session**:
   - `LiveBotController.step_tick()` checks if an active session exists with `status == "RUNNING"`. If not, no trades are scanned or generated.
   - Manual order submission endpoints (`/api/dashboard/order`, `/api/broker/order`) reject orders if no active session is running.
3. **Strict Basket Containment**:
   - The bot will NEVER generate or accept an order for any ticker not in `session.instruments`.
4. **Session Expiry & Lifecycle Enforcement**:
   - On each bot tick, if `session.expires_at` is set and `now_utc >= session.expires_at`:
     - Transition session to `"COMPLETED"`.
     - Set `ended_at = now_utc`.
     - Execute `session_end_policy`:
       - If `"CLOSE_ALL"`: Call `broker.close_all_positions(reason="SESSION_EXPIRED")`.
       - If `"KEEP_OPEN"`: Positions remain open for manual trader closure.
     - Halt autonomous trade loop.
     - Emit log event: `"SESSION EXPIRED: Run duration elapsed. Bot halted without silent extension."`
5. **Market Data Staleness Guardrail**:
   - If a quote for an approved instrument is stale (`is_stale == True` or `age_seconds > max_staleness`):
     - Block all new trade entries for that symbol.
     - Do NOT invent or interpolate synthetic prices.
     - Keep existing position open with last confirmed price until fresh market ticks arrive.

---

## 4. Bot Runtime Integration Design

### 4.1 Session Lifecycle State Machine

```
              [ User completes Setup Wizard ]
                            │
                            ▼
                     ┌──────────────┐
                     │   CREATED    │
                     └──────┬───────┘
                            │  POST /start
                            ▼
              ┌───────────────────────────┐
              │          RUNNING          │◄───────────┐
              └───┬───────────┬─────────┬─┘            │
                  │           │         │              │
      POST /pause │           │ Expiry  │ POST /stop   │ POST /resume
                  ▼           │ or Kill │              │
           ┌──────────┐       │         ▼              │
           │  PAUSED  ├───────┼─►┌─────────────┐       │
           └────┬─────┘       │  │   STOPPED   │       │
                │             │  └─────────────┘       │
                └─────────────┼────────────────────────┘
                              ▼
                     ┌─────────────────┐
                     │    COMPLETED    │
                     │  (or HALTED)    │
                     └─────────────────┘
```

### 4.2 Integration into `LiveBotController`

Add a dedicated `SessionManager` instance to `LiveBotController`:

```python
class LiveBotController:
    def __init__(self, engine, broker, ...):
        ...
        self.session_manager = SessionManager(ledger=self.broker.ledger)
        self.active_session: Optional[TradingSession] = None
```

In `step_tick()`:
```python
def step_tick(self, custom_shock_pct: Optional[float] = None) -> Dict:
    # 0. Check Session Lifecycle
    self.active_session = self.session_manager.get_active_session()
    if self.active_session and self.active_session.status == "RUNNING":
        # Check Expiration
        if self.active_session.is_expired():
            self.session_manager.expire_session(self.active_session.id, broker=self.broker)
            self.log_event("SESSION", f"Session {self.active_session.id} expired. Enforced {self.active_session.session_end_policy}.")
            self.is_running = False

    # 1. Physical exchange session checks...
    ...
    # 8. Trade Generation: Guarded by active session!
    if self.is_running and self.active_session and self.active_session.status == "RUNNING":
        # Restrict candidates strictly to self.active_session.instruments
        approved_tickers = set(self.active_session.instruments)
        candidates = [c for c in candidates if c[0] in approved_tickers]
        ...
```

### 4.3 Dashboard Controls Mapping

| Dashboard Control | API Endpoint | Bot Controller Action | Session State Transition |
| :--- | :--- | :--- | :--- |
| **START** | `POST /api/sessions/{id}/start` | Re-seeds watchlist with approved basket, sets `is_running = True`, resets/allocates capital | `CREATED` -> `RUNNING` |
| **PAUSE** | `POST /api/sessions/{id}/pause` | Sets `is_running = False`. Keeps position monitoring & stops/targets active | `RUNNING` -> `PAUSED` |
| **RESUME** | `POST /api/sessions/{id}/resume`| Sets `is_running = True`, offsets pause duration in `expires_at` | `PAUSED` -> `RUNNING` |
| **STOP** | `POST /api/sessions/{id}/stop` | Sets `is_running = False`, triggers session-end policy (flatten if `CLOSE_ALL`) | `RUNNING`/`PAUSED` -> `STOPPED` |

---

## 5. Proposed File Modifications & Additions

To keep the codebase modular and clean:

1. **New Module: `src/execution/session_manager.py`**:
   - `TradingSession` data class and database mapping.
   - `SessionManager` class: handles database CRUD, state transitions, validation, expiration logic, and performance aggregation.
2. **Database Updates in `src/execution/broker.py`**:
   - Enhance `TradingLedgerDB._init_db()` to create `trading_sessions` table and add `session_id` column to `orders`, `positions`, `trades`, and `equity_history`.
   - Update `PaperBroker.open_position()` and `queue_pre_market_order()` to accept `session_id: Optional[str] = None`.
3. **API Updates in `server.py`**:
   - Register Pydantic request models (`SessionCreateRequest`, `SessionUpdateRequest`, etc.).
   - Mount new REST routes: `/api/sessions`, `/api/sessions/active`, `/api/sessions/{session_id}`, `/api/sessions/{session_id}/start`, `/pause`, `/resume`, `/stop`, `/recommendations`, `/performance`.
   - Ensure `/api/sessions/status` remains functional for physical exchange queries.
4. **Integration in `src/execution/live_bot.py`**:
   - Connect `LiveBotController` to `SessionManager`.
   - Enforce active session check, instrument basket boundaries, and session expiration in `step_tick()`.
5. **New Test Suite: `tests/test_trading_session_lifecycle.py`**:
   - Unit and integration tests covering parameter validation, state transitions, basket confinement, duration expiration, and session-end policies.

---

## 6. Verification Plan

1. **Database Schema Verification**:
   - Run SQLite migrations and verify tables and indices with Python `sqlite3`.
   - Verify existing tables (`accounts`, `positions`, `orders`, `trades`) retain all data without schema mismatch.
2. **API Endpoint Verification**:
   - Use `FastAPI` `TestClient` to test all endpoints:
     - Invalid capital rejection (negative, zero, above max).
     - Currency mismatch rejection (e.g., USD for Indian Equities).
     - Cross-market ticker rejection (e.g., RELIANCE.NS in US Equities).
     - Full lifecycle transitions: `CREATED` -> `RUNNING` -> `PAUSED` -> `RUNNING` -> `STOPPED`.
     - Expiry enforcement when mock time advances past `expires_at`.
3. **Regression Verification**:
   - Run existing test suites:
     - `py -m pytest tests/test_market_sessions.py` (Must pass 35/35).
     - `py -m pytest tests/test_milestone_m2_sessions.py` (Must pass 5/5).
     - `py -m pytest tests/test_e2e_platform.py` (Must pass 42/42).
