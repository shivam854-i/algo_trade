# Handoff Report: Backend Architecture Blueprint (R2 & R3)
**Module**: SYNAPSE-TITAN Backend Architecture & Session Lifecycle Management
**Author**: Backend Architecture Explorer (`teamwork_explorer`)
**Target Directory**: `C:\Users\Shivam\Desktop\trade_bot`
**Working Directory**: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\explorer_survey_backend`
**Date**: 2026-11-05

---

## 1. Observation

Direct observations and evidence from the codebase investigation:

1. **Server & Lifecycle Architecture (`server.py`)**:
   - `server.py:43-54`: Global lifespan initializes `MarketPredictionEngine()`, `BacktestEngine()`, and `LiveBotController(engine, broker=broker_engine)`.
   - `server.py:726-731`: An existing endpoint `@app.get("/api/sessions/status", tags=["Sessions"])` returns physical exchange session statuses (`bot.get_all_market_sessions()`). Parameterized trading session routes (e.g. `/api/sessions/{session_id}`) must be registered carefully so they do not collide with this existing physical session status route.
   - `server.py:827-837`: `toggle_bot_running()` toggles `bot.is_running` but has no concept of an active session, session duration, or user configuration.

2. **Database Schema & Migrations (`src/execution/broker.py`)**:
   - `src/execution/broker.py:75-271`: `TradingLedgerDB` connects to `data/trading_ledger.db`. It manages tables: `accounts`, `positions`, `trades`, `orders`, and `equity_history`.
   - `src/execution/broker.py:112-119, 145-157, 181-189, 223-237`: Schema migrations are handled idempotently via `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ... ADD COLUMN ...` inside `try...except Exception: pass` blocks.
   - Querying `data/trading_ledger.db` confirms existing tables:
     `['accounts', 'positions', 'trades', 'users', 'orders', 'equity_history']`.

3. **Autonomous Bot Loop & State (`src/execution/live_bot.py`)**:
   - `src/execution/live_bot.py:780-1059`: `LiveBotController.step_tick()` executes the 10-step autonomous loop. It checks `self.is_running` and iterates over `self.armed_tickers`.
   - `src/execution/live_bot.py:824-828`: When an exchange is closed and not in simulation mode, price ticks are frozen and orders are queued to `PRE_MARKET_PENDING`.
   - `src/execution/live_bot.py:891-910`: Genuine market quotes are validated; stale quotes (`quote.is_stale`) block new entries without fabricating synthetic prices.

4. **Market Timings & Jurisdiction Detection (`src/execution/market_sessions.py`)**:
   - `src/execution/market_sessions.py:24-31`: 6-state exchange state machine: `OPEN`, `PRE_MARKET`, `POST_MARKET`, `CLOSED`, `WEEKEND`, `HOLIDAY`.
   - `src/execution/market_sessions.py:38-70` in `tests/test_market_sessions.py`: Jurisdiction detection classifies `.NS` / `.BO` as `NSE_CASH`, standard US tickers as `US_EQUITIES`, `=F` as `COMMODITY`, `-USD` as `CRYPTO`, and `=X` as `FOREX`.

5. **Existing Test Suite Execution**:
   - `tests/test_market_sessions.py`: 35 passed in 0.73s.
   - `tests/test_milestone_m2_sessions.py`: 5 passed.
   - `tests/test_e2e_platform.py`: 42 passed in 29.93s.
   - Frontend `vitest run` in `frontend/`: 22 passed in 1.97s.

---

## 2. Logic Chain

From the direct observations above, the following logical conclusions emerge:

1. **Database Schema Coexistence** (supported by Observation 2):
   - Because `TradingLedgerDB` uses the pattern of `CREATE TABLE IF NOT EXISTS` followed by guarded `ALTER TABLE ADD COLUMN`, introducing a new `trading_sessions` table and adding `session_id TEXT` to `orders`, `positions`, `trades`, and `equity_history` will be completely non-destructive and 100% backward-compatible. Existing test suites using isolated temporary databases or the default database will not experience schema conflicts.

2. **Route Conflict Prevention** (supported by Observation 1):
   - In FastAPI, static route paths match before path parameters if declared earlier in the router or if disambiguated. Because `GET /api/sessions/status` is already used by `tests/test_milestone_m2_sessions.py` to inspect physical exchange sessions, the new trading session routes (`/api/sessions`, `/api/sessions/active`, `/api/sessions/recommendations`) must be registered before `/api/sessions/{session_id}`.

3. **Session Lifecycle Enforcement in Autonomous Bot** (supported by Observation 1 and 3):
   - Currently, `live_bot.py` trades whenever `self.is_running is True` and `self.armed_tickers` contains symbols.
   - To fulfill R2 and R3, `live_bot.py` must check for an active `TradingSession` whose status is `RUNNING`.
   - If no session is active, or if the session is `PAUSED`, `STOPPED`, or `COMPLETED`, `step_tick` must halt autonomous new order execution.
   - In `step_tick`, an expiration check `now_utc >= session.expires_at` must evaluate on every tick, triggering the configured `session_end_policy` (`CLOSE_ALL` via `broker.close_all_positions` or `KEEP_OPEN`) and transitioning the session status to `COMPLETED`.

4. **Independent Backend Validation** (supported by Observation 4):
   - Using `MarketCalendarManager.detect_market_type(ticker)`, the backend can independently verify that every instrument in the requested basket matches the selected market jurisdiction (e.g. rejecting `AAPL` in an `INDIAN_NSE` session).
   - Capital currency validation (`INR` for `INDIAN_NSE`, `USD` for `US_EQUITIES`, `CRYPTO`, `FOREX`, `COMMODITIES`) can be enforced independently before any session record is written.

---

## 3. Caveats

1. **Quantitative Modules (R4)**: The quantitative modules (`src/strategy/universe_selector.py`, `trade_evaluator.py`, `trade_ranker.py`, `portfolio_selector.py`, and `decision_explainer.py`) are assigned to the Quantitative Specialist agent. The recommendation endpoint `POST /api/sessions/recommendations` designed here will interface with `UniverseSelector` once implemented. A robust fallback/mock provider has been specified in the interim.
2. **Horizon Mapping (R5)**: Strategy parameter binding for different horizons (`1h`, `1d`, `1wk`) dynamically affects feature window lengths and bar intervals in `src/pipeline.py`. The session model stores these parameters in `strategy_config` and applies them when starting the session.
3. **Multi-User Isolation**: The current system operates with a single default paper account (`PAPER_DEFAULT` / `DEFAULT_USER`). The `TradingSession` model includes `user_id` and `account_id` to future-proof multi-tenant SaaS expansion, but initial execution defaults to the local paper ledger.

---

## 4. Conclusion & Actionable Blueprint

### 4.1 Recommended Implementation Structure: `src/execution/session_manager.py`
Create a dedicated `SessionManager` module encapsulating:
1. `TradingSession` dataclass with state serialization, duration countdown, and expiration detection.
2. `SessionManager` class with SQLite persistence methods:
   - `create_session(data: SessionCreateRequest) -> TradingSession`
   - `get_active_session() -> Optional[TradingSession]`
   - `get_session(session_id: str) -> Optional[TradingSession]`
   - `list_sessions(status, market, limit) -> List[TradingSession]`
   - `update_session(session_id, data: SessionUpdateRequest) -> TradingSession`
   - `start_session(session_id: str, bot: LiveBotController) -> TradingSession`
   - `pause_session(session_id: str, bot: LiveBotController) -> TradingSession`
   - `resume_session(session_id: str, bot: LiveBotController) -> TradingSession`
   - `stop_session(session_id: str, bot: LiveBotController, reason: str = "MANUAL_STOP") -> TradingSession`
   - `check_and_enforce_expiry(bot: LiveBotController) -> Optional[TradingSession]`
   - `update_session_metrics(session_id: str, metrics: Dict[str, Any]) -> None`

### 4.2 SQLite Table Schema
Add to `TradingLedgerDB._init_db()` in `src/execution/broker.py`:
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

ALTER TABLE orders ADD COLUMN session_id TEXT;
ALTER TABLE positions ADD COLUMN session_id TEXT;
ALTER TABLE trades ADD COLUMN session_id TEXT;
ALTER TABLE equity_history ADD COLUMN session_id TEXT;
```

### 4.3 REST API Endpoints in `server.py`
Add to `server.py`:
- `POST /api/sessions` — Create session with independent validation.
- `GET /api/sessions/active` — Get currently active session or null.
- `GET /api/sessions/{session_id}` — Get session by ID.
- `GET /api/sessions` — List sessions with query filters.
- `PUT /api/sessions/{session_id}` — Update session parameters (in CREATED or PAUSED state).
- `POST /api/sessions/{session_id}/start` — Launch session, arm bot, allocate capital.
- `POST /api/sessions/{session_id}/pause` — Pause session, halt new entries, keep positions monitored.
- `POST /api/sessions/{session_id}/resume` — Resume session, adjust expiry countdown.
- `POST /api/sessions/{session_id}/stop` — Stop session, execute session-end policy.
- `POST /api/sessions/recommendations` — Auto-select recommended stock basket with rationales.
- `GET /api/sessions/{session_id}/performance` — Financial KPIs, P&L, drawdown, trade history.

---

## 5. Verification Method

To independently verify the implementation:

1. **Database Schema Verification**:
   ```powershell
   py -c "import sqlite3; conn = sqlite3.connect('data/trading_ledger.db'); cursor = conn.cursor(); cursor.execute('PRAGMA table_info(trading_sessions)'); print('trading_sessions columns:', [r[1] for r in cursor.fetchall()])"
   ```
   *Expected*: Column list matches the schema above, including `id`, `market`, `instruments`, `horizon`, `duration_minutes`, `session_end_policy`, `allocated_capital`, `currency`, `status`, etc.

2. **Automated Backend Test Suite Execution**:
   Run the full backend test suite using the project's Windows `py` interpreter:
   ```powershell
   cd C:\Users\Shivam\Desktop\trade_bot
   py -m pytest tests/test_market_sessions.py
   py -m pytest tests/test_milestone_m2_sessions.py
   py -m pytest tests/test_e2e_platform.py
   ```
   *Expected*: All existing tests continue to pass with 0 regressions.

3. **New Session Lifecycle Tests**:
   Create and execute `tests/test_trading_session_lifecycle.py` verifying:
   - Currency and market validation (rejection of currency mismatch).
   - Instrument jurisdiction matching (rejection of non-market symbols).
   - State transitions: `CREATED` -> `RUNNING` -> `PAUSED` -> `RUNNING` -> `STOPPED`.
   - Duration expiration: `expires_at` reached triggers `session_end_policy` and terminates without silent extension.
   - Refusal of execution without active session.
   - Strict confinement to approved instrument basket.

4. **Frontend Verification**:
   ```powershell
   cd C:\Users\Shivam\Desktop\trade_bot\frontend
   npm test
   npm run build
   ```
   *Expected*: All vitest tests pass and TypeScript build succeeds without errors.
