# Handoff Report: Session Model & Database Migrations (Milestone 2 - Part A)

**Module**: SYNAPSE-TITAN Backend Architecture & Session Lifecycle Management  
**Author**: Session Model & SQLite Migration Explorer (`teamwork_explorer`)  
**Target Repository**: `C:\Users\Shivam\Desktop\trade_bot`  
**Working Directory**: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_explorer_1`  
**Date**: 2026-11-05  

---

## 1. Observation

Direct observations and evidence from the codebase investigation:

1. **Absence of Dedicated Session Manager (`src/execution/`)**:
   - `list_dir` on `C:\Users\Shivam\Desktop\trade_bot\src\execution` confirms files:
     `__init__.py`, `auth.py`, `broker.py`, `frictions.py`, `guardrails.py`, `live_bot.py`, `market_sessions.py`.
   - `src/execution/session_manager.py` does not currently exist.
   - `tests/test_trading_session_lifecycle.py` does not currently exist.

2. **Existing Database Schema & Migration Pattern (`src/execution/broker.py`)**:
   - `src/execution/broker.py:75-95`: `TradingLedgerDB` connects to `data/trading_ledger.db` and executes `self._init_db()`.
   - `src/execution/broker.py:98-256`: Tables are created with `CREATE TABLE IF NOT EXISTS`: `accounts`, `positions`, `trades`, `orders`, and `equity_history`.
   - `src/execution/broker.py:112-119, 145-157, 181-189, 223-237`: Schema migrations are performed via guarded `ALTER TABLE ... ADD COLUMN ...` statements inside `try...except Exception: pass` loops:
     ```python
     for col_sql in [
         "ALTER TABLE orders ADD COLUMN limit_price REAL DEFAULT 0.0",
         "ALTER TABLE orders ADD COLUMN filled_shares REAL DEFAULT 0.0",
         ...
     ]:
         try:
             cursor.execute(col_sql)
         except Exception:
             pass
     ```
   - Current schema of `orders`, `positions`, `trades`, and `equity_history` has no `session_id` column.

3. **Autonomous Bot Loop Execution (`src/execution/live_bot.py`)**:
   - `src/execution/live_bot.py:160-197`: `LiveBotController.__init__()` initializes `self.watchlist` and `self.armed_tickers` to default US equities (`DEFAULT_US_EQUITIES`), with `self.is_running = True`. It has no concept of an active session, session duration, allocated session capital, or expiry policy.
   - `src/execution/live_bot.py:960-985`: In `step_tick()`, the bot trades whenever `self.is_running and self.armed_tickers`. It does not restrict trades to a user-confirmed session or enforce session duration limits.

4. **API Route Namespace & Conflict Risk (`server.py`)**:
   - `server.py:726-731`: An existing physical exchange route is declared:
     ```python
     @app.get("/api/sessions/status", tags=["Sessions"])
     def get_sessions_status():
         bot = _get_live_bot()
         return bot.get_all_market_sessions()
     ```
   - If a parameterized route `@app.get("/api/sessions/{session_id}")` is registered without proper ordering or path regex, requests to `/api/sessions/status` could be intercepted with `session_id = "status"`.

5. **Existing Acceptance & Challenger Test Suites**:
   - Ran `cd C:\Users\Shivam\Desktop\trade_bot; py -m pytest tests/test_milestone_m2_sessions.py`:
     `5 passed, 79 warnings in 34.88s` (Exit code 0).
   - Ran `cd C:\Users\Shivam\Desktop\trade_bot; py -m pytest tests/test_strategy_horizon_mapper.py`:
     `6 passed, 1 warning in 4.46s` (Exit code 0).
   - Test suites routinely use temporary SQLite ledgers via `TradingLedgerDB(db_path=...)` or `PaperBroker(account_id=...)`.

---

## 2. Logic Chain

From the direct observations above, the following logical conclusions are derived:

1. **Non-Destructive Coexistence via Guarded Alteration** (supported by Observation 2):
   - By creating the `trading_sessions` table with `CREATE TABLE IF NOT EXISTS` and adding `session_id TEXT` to `orders`, `positions`, `trades`, and `equity_history` within `try...except Exception: pass` blocks, existing test databases and production SQLite files are upgraded without data loss, lockups, or migration failures.
   - Updating the base `CREATE TABLE IF NOT EXISTS` statements simultaneously guarantees that freshly created isolated databases (such as those in `pytest` fixtures) instantly contain the `session_id` columns and indexes natively.

2. **Decoupled Architecture between `TradingSession` and `SessionManager`** (supported by Observation 1 and 3):
   - Isolating `TradingSession` (pure data model, state machine definitions, serialization, countdown calculation) from `SessionManager` (SQLite transactions, CRUD, bot lifecycle binding, parameter validation) ensures clean unit testability without requiring live market engines or database connections for pure state math.

3. **Time Dilation on Pause/Resume** (supported by Observation 3):
   - A naive implementation with a static `expires_at` would penalize the user during `PAUSED` periods, as the clock would continue running.
   - To achieve an accurate countdown, `expires_at` must be shifted forward by `accumulated_pause_seconds` upon `resume_session()`. While paused, `remaining_seconds()` must return the frozen duration relative to `paused_at`.

4. **Single Active Session Constraint** (supported by Observation 3):
   - `LiveBotController` manages a single virtual brokerage instance (`broker_engine`). If multiple sessions were active simultaneously on the same paper account, capital allocation and position tracking would conflict.
   - Therefore, `SessionManager.start_session()` must enforce that only ONE session can be in `RUNNING` or `PAUSED` state per account at any time, returning a descriptive `RuntimeError` if an active session collision occurs.

5. **Route Disambiguation Strategy** (supported by Observation 4):
   - In FastAPI, static route paths match before parameterized paths only if declared prior to the parameterized routes. In Milestone 2 Part B, `/api/sessions/status`, `/api/sessions/active`, and `/api/sessions/recommendations` must be declared before `/api/sessions/{session_id}`.

---

## 3. Caveats

1. **FastAPI Endpoints (Milestone 2 Part B)**: This report focuses exclusively on the data model, database migrations, and `SessionManager` persistence operations (Milestone 2 Part A). The 11 FastAPI REST endpoints in `server.py` and the autonomous loop hooks in `live_bot.py` are part of subsequent Milestone 2 phases and will consume the interfaces defined here.
2. **Multi-Tenant Account Scope**: While `user_id` and `account_id` are natively modeled on `trading_sessions` and foreign-keyed on transactional tables, the current system defaults to `user_id="DEFAULT_USER"` and `account_id="PAPER_DEFAULT"`. Multi-tenant isolation is supported at the schema level without breaking existing single-account defaults.
3. **Database Concurrency**: SQLite utilizes table-level locking in default journal mode. `TradingLedgerDB` uses short-lived connections per operation with `with self._get_connection() as conn:`. All session update transactions are short and isolated.

---

## 4. Conclusion & Actionable Implementation Blueprints

### 4.1 Implementation Blueprint: `src/execution/session_manager.py`

Create `src/execution/session_manager.py` with the following complete, production-grade implementation:

```python
"""SYNAPSE-TITAN Trading Session Model & Lifecycle Manager.

Manages user-configured paper trading sessions, state transitions,
SQLite persistence, countdown timers, and end-policy enforcement.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Union
import uuid

from src.execution.broker import TradingLedgerDB


class SessionStatus(str, Enum):
    """Lifecycle states for a TradingSession."""
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"


class DurationType(str, Enum):
    """Session duration classification."""
    FIXED = "FIXED"
    CUSTOM = "CUSTOM"
    MANUAL_STOP = "MANUAL_STOP"


class SessionEndPolicy(str, Enum):
    """Policy executed when a session completes or stops."""
    CLOSE_ALL = "CLOSE_ALL"
    KEEP_OPEN = "KEEP_OPEN"


class SessionMarket(str, Enum):
    """Supported market jurisdictions."""
    INDIAN_NSE = "INDIAN_NSE"
    US_EQUITIES = "US_EQUITIES"
    CRYPTO = "CRYPTO"
    FOREX = "FOREX"
    COMMODITIES = "COMMODITIES"


class SessionCurrency(str, Enum):
    """Supported virtual currencies."""
    USD = "USD"
    INR = "INR"


class TradingHorizon(str, Enum):
    """Holding horizon classifications."""
    ONE_HOUR = "1h"
    ONE_DAY = "1d"
    ONE_WEEK = "1wk"


@dataclass
class TradingSession:
    """Production data model representing an isolated paper-trading session."""

    # Primary Identifiers & Tenancy
    id: str
    market: str
    instruments: List[str]
    horizon: str
    duration_type: str
    allocated_capital: float
    currency: str
    user_id: str = "DEFAULT_USER"
    account_id: str = "PAPER_DEFAULT"
    name: Optional[str] = None

    # Duration & Expiry Policy
    duration_minutes: Optional[int] = None
    session_end_policy: str = "CLOSE_ALL"

    # Strategy & Risk Configurations
    strategy_config: Dict[str, Any] = field(default_factory=dict)
    risk_config: Dict[str, Any] = field(default_factory=dict)

    # State & Timestamps
    status: str = "CREATED"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    paused_at: Optional[str] = None
    resumed_at: Optional[str] = None
    ended_at: Optional[str] = None
    expires_at: Optional[str] = None
    accumulated_pause_seconds: int = 0

    # Live Telemetry & Metrics
    current_metrics: Dict[str, Any] = field(default_factory=dict)
    last_heartbeat_at: Optional[str] = None

    # ----------------- Derived Properties ----------------- #

    @property
    def is_active(self) -> bool:
        """Returns True if session is currently operational (RUNNING or PAUSED)."""
        return self.status in (SessionStatus.RUNNING.value, SessionStatus.PAUSED.value)

    @property
    def is_running(self) -> bool:
        """Returns True if session is currently actively trading."""
        return self.status == SessionStatus.RUNNING.value

    @property
    def is_paused(self) -> bool:
        """Returns True if session is currently suspended."""
        return self.status == SessionStatus.PAUSED.value

    @property
    def is_terminal(self) -> bool:
        """Returns True if session has reached a final state (COMPLETED or STOPPED)."""
        return self.status in (SessionStatus.COMPLETED.value, SessionStatus.STOPPED.value)

    def is_expired(self, now_utc: Optional[datetime] = None) -> bool:
        """Determines whether the session duration has elapsed."""
        if self.duration_type == DurationType.MANUAL_STOP.value or not self.expires_at:
            return False
        if self.status in (SessionStatus.COMPLETED.value, SessionStatus.STOPPED.value):
            return True
        now = now_utc or datetime.now(timezone.utc)
        exp = datetime.fromisoformat(self.expires_at)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return now >= exp

    def remaining_seconds(self, now_utc: Optional[datetime] = None) -> Optional[int]:
        """Calculates live remaining seconds, freezing countdown during PAUSED state."""
        if self.duration_type == DurationType.MANUAL_STOP.value or not self.expires_at:
            return None
        if self.is_terminal:
            return 0
        if self.status == SessionStatus.PAUSED.value and self.paused_at:
            # Frozen countdown relative to paused_at
            p_dt = datetime.fromisoformat(self.paused_at)
            if p_dt.tzinfo is None:
                p_dt = p_dt.replace(tzinfo=timezone.utc)
            exp_dt = datetime.fromisoformat(self.expires_at)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            return max(0, int((exp_dt - p_dt).total_seconds()))

        now = now_utc or datetime.now(timezone.utc)
        exp_dt = datetime.fromisoformat(self.expires_at)
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        return max(0, int((exp_dt - now).total_seconds()))

    # ----------------- Serialization Methods ----------------- #

    def to_dict(self) -> Dict[str, Any]:
        """Serializes session dataclass into a clean dictionary with telemetry properties."""
        d = asdict(self)
        d["is_active"] = self.is_active
        d["is_running"] = self.is_running
        d["is_paused"] = self.is_paused
        d["is_terminal"] = self.is_terminal
        d["is_expired"] = self.is_expired()
        d["remaining_seconds"] = self.remaining_seconds()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradingSession":
        """Deserializes dictionary into TradingSession dataclass with robust type safety."""
        clean = dict(data)
        for key in ["is_active", "is_running", "is_paused", "is_terminal", "is_expired", "remaining_seconds"]:
            clean.pop(key, None)

        if isinstance(clean.get("instruments"), str):
            try:
                clean["instruments"] = json.loads(clean["instruments"])
            except Exception:
                clean["instruments"] = []
        if isinstance(clean.get("strategy_config"), str):
            try:
                clean["strategy_config"] = json.loads(clean["strategy_config"])
            except Exception:
                clean["strategy_config"] = {}
        if isinstance(clean.get("risk_config"), str):
            try:
                clean["risk_config"] = json.loads(clean["risk_config"])
            except Exception:
                clean["risk_config"] = {}
        if isinstance(clean.get("current_metrics"), str):
            try:
                clean["current_metrics"] = json.loads(clean["current_metrics"])
            except Exception:
                clean["current_metrics"] = {}

        return cls(**clean)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TradingSession":
        """Reconstructs TradingSession directly from an SQLite row."""
        return cls.from_dict(dict(row))


class SessionManager:
    """SQLite-backed transactional persistence and state management for TradingSessions."""

    def __init__(self, ledger: Optional[TradingLedgerDB] = None, db_path: Optional[Path] = None):
        if ledger is not None:
            self.ledger = ledger
        else:
            self.ledger = TradingLedgerDB(db_path=db_path)

    # ----------------- Independent Backend Validation ----------------- #

    def validate_session_parameters(
        self,
        market: str,
        currency: str,
        instruments: List[str],
        allocated_capital: float,
        horizon: str,
        duration_type: str,
        duration_minutes: Optional[int],
        session_end_policy: str,
    ) -> None:
        """Validates all session configuration parameters independently of frontend checks."""
        # 1. Market validation
        if market not in [m.value for m in SessionMarket]:
            raise ValueError(f"Unsupported market: {market}. Must be one of {[m.value for m in SessionMarket]}")

        # 2. Currency validation matching market
        expected_currency = "INR" if market == SessionMarket.INDIAN_NSE.value else "USD"
        if currency.upper() != expected_currency:
            raise ValueError(
                f"Currency mismatch: Market {market} requires currency {expected_currency}, got {currency}"
            )

        # 3. Capital validation
        if allocated_capital is None or float(allocated_capital) <= 0:
            raise ValueError(f"Allocated capital must be strictly positive, got {allocated_capital}")
        min_cap = 5000.0 if currency == "INR" else 100.0
        max_cap = 1_000_000_000.0 if currency == "INR" else 10_000_000.0
        if not (min_cap <= float(allocated_capital) <= max_cap):
            raise ValueError(f"Allocated capital {allocated_capital} outside allowed limits [{min_cap}, {max_cap}] {currency}")

        # 4. Instrument list validation
        if not instruments or not isinstance(instruments, list):
            raise ValueError("Instruments must be a non-empty list of ticker symbols")
        unique_tickers = list(dict.fromkeys([str(t).upper().strip() for t in instruments if str(t).strip()]))
        if not unique_tickers:
            raise ValueError("Instruments basket must contain at least one valid ticker symbol")

        # 5. Jurisdiction containment check
        for tk in unique_tickers:
            if market == SessionMarket.INDIAN_NSE.value:
                if not (tk.endswith(".NS") or tk.endswith(".BO")):
                    raise ValueError(f"Ticker {tk} does not belong to market {market} (expected .NS or .BO suffix)")
            elif market == SessionMarket.CRYPTO.value:
                if not tk.endswith("-USD"):
                    raise ValueError(f"Ticker {tk} does not belong to market {market} (expected -USD suffix)")
            elif market == SessionMarket.COMMODITIES.value:
                if not tk.endswith("=F"):
                    raise ValueError(f"Ticker {tk} does not belong to market {market} (expected =F suffix)")
            elif market == SessionMarket.FOREX.value:
                if not tk.endswith("=X"):
                    raise ValueError(f"Ticker {tk} does not belong to market {market} (expected =X suffix)")
            elif market == SessionMarket.US_EQUITIES.value:
                if "." in tk or "=" in tk or "-" in tk:
                    raise ValueError(f"Ticker {tk} does not belong to market {market}")

        # 6. Horizon validation
        if horizon not in [h.value for h in TradingHorizon]:
            raise ValueError(f"Invalid horizon: {horizon}. Must be one of {[h.value for h in TradingHorizon]}")

        # 7. Duration validation
        if duration_type not in [d.value for d in DurationType]:
            raise ValueError(f"Invalid duration_type: {duration_type}. Must be one of {[d.value for d in DurationType]}")
        if duration_type in (DurationType.FIXED.value, DurationType.CUSTOM.value):
            if duration_minutes is None or int(duration_minutes) <= 0:
                raise ValueError(f"duration_minutes must be a positive integer for duration_type {duration_type}")
            if int(duration_minutes) > 525600:
                raise ValueError("duration_minutes exceeds maximum allowable duration (1 year)")

        # 8. End policy validation
        if session_end_policy not in [p.value for p in SessionEndPolicy]:
            raise ValueError(f"Invalid session_end_policy: {session_end_policy}")

    # ----------------- CRUD Operations ----------------- #

    def create_session(self, data: Dict[str, Any]) -> TradingSession:
        """Validates configuration, generates session ID, and creates an SQLite record in CREATED state."""
        market = str(data.get("market", "")).upper()
        currency = str(data.get("currency", "USD")).upper()
        instruments = data.get("instruments", [])
        allocated_capital = float(data.get("allocated_capital", 0.0))
        horizon = str(data.get("horizon", "1d"))
        duration_type = str(data.get("duration_type", "FIXED")).upper()
        duration_minutes = data.get("duration_minutes")
        if duration_minutes is not None:
            duration_minutes = int(duration_minutes)
        session_end_policy = str(data.get("session_end_policy", "CLOSE_ALL")).upper()

        self.validate_session_parameters(
            market=market,
            currency=currency,
            instruments=instruments,
            allocated_capital=allocated_capital,
            horizon=horizon,
            duration_type=duration_type,
            duration_minutes=duration_minutes,
            session_end_policy=session_end_policy,
        )

        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now(timezone.utc).isoformat()
        user_id = str(data.get("user_id", "DEFAULT_USER"))
        account_id = str(data.get("account_id", "PAPER_DEFAULT"))
        name = data.get("name") or f"{market} {horizon} Session"

        strategy_cfg = data.get("strategy_config") or {}
        risk_cfg = data.get("risk_config") or {}
        metrics = {
            "initial_capital": allocated_capital,
            "current_cash": allocated_capital,
            "invested_equity": 0.0,
            "total_equity": allocated_capital,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "total_trades": 0,
            "winning_trades": 0,
            "win_rate_pct": 0.0,
        }

        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trading_sessions (
                    id, user_id, account_id, name, market, instruments, horizon,
                    duration_type, duration_minutes, session_end_policy, allocated_capital,
                    currency, strategy_config, risk_config, status, created_at,
                    accumulated_pause_seconds, current_metrics, last_heartbeat_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CREATED', ?, 0, ?, ?)
            """, (
                session_id, user_id, account_id, name, market, json.dumps(instruments),
                horizon, duration_type, duration_minutes, session_end_policy, allocated_capital,
                currency, json.dumps(strategy_cfg), json.dumps(risk_cfg), now_str,
                json.dumps(metrics), now_str
            ))
            conn.commit()

        return self.get_session(session_id)

    def get_session(self, session_id: str) -> Optional[TradingSession]:
        """Fetches a session by its unique ID."""
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trading_sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return TradingSession.from_row(row)

    def get_active_session(self, account_id: Optional[str] = None) -> Optional[TradingSession]:
        """Retrieves the currently operational session (RUNNING or PAUSED) for an account."""
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            if account_id:
                cursor.execute("""
                    SELECT * FROM trading_sessions
                    WHERE account_id = ? AND status IN ('RUNNING', 'PAUSED')
                    ORDER BY started_at DESC, created_at DESC LIMIT 1
                """, (account_id,))
            else:
                cursor.execute("""
                    SELECT * FROM trading_sessions
                    WHERE status IN ('RUNNING', 'PAUSED')
                    ORDER BY started_at DESC, created_at DESC LIMIT 1
                """)
            row = cursor.fetchone()
            return TradingSession.from_row(row) if row else None

    def list_sessions(
        self,
        status: Optional[str] = None,
        market: Optional[str] = None,
        account_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[TradingSession]:
        """Lists sessions with optional multi-predicate filtering and pagination."""
        query = "SELECT * FROM trading_sessions WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status.upper())
        if market:
            query += " AND market = ?"
            params.append(market.upper())
        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [TradingSession.from_row(r) for r in rows]

    def update_session(self, session_id: str, updates: Dict[str, Any]) -> TradingSession:
        """Updates parameters of a session in CREATED or PAUSED state."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Session #{session_id} not found")
        if session.status not in (SessionStatus.CREATED.value, SessionStatus.PAUSED.value):
            raise ValueError(f"Cannot update session #{session_id} while in state '{session.status}'")

        allowed_fields = [
            "name", "instruments", "horizon", "duration_minutes",
            "session_end_policy", "allocated_capital", "strategy_config", "risk_config"
        ]
        set_clauses = []
        params = []
        for k in allowed_fields:
            if k in updates:
                val = updates[k]
                if k in ("instruments", "strategy_config", "risk_config") and not isinstance(val, str):
                    val = json.dumps(val)
                set_clauses.append(f"{k} = ?")
                params.append(val)

        if not set_clauses:
            return session

        params.append(session_id)
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE trading_sessions SET {', '.join(set_clauses)} WHERE id = ?", tuple(params))
            conn.commit()

        return self.get_session(session_id)

    # ----------------- Lifecycle State Machine Actions ----------------- #

    def start_session(self, session_id: str, bot: Optional[Any] = None) -> TradingSession:
        """Launches a CREATED session into RUNNING state, calculating expires_at and arming the bot."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Session #{session_id} not found")
        if session.status != SessionStatus.CREATED.value:
            raise ValueError(f"Cannot start session in state '{session.status}'. Must be in 'CREATED' state.")

        active = self.get_active_session(session.account_id)
        if active and active.id != session_id:
            raise RuntimeError(
                f"Cannot start session #{session_id}: Account already has active session #{active.id} ({active.status}). "
                "Pause or stop the active session first."
            )

        now_utc = datetime.now(timezone.utc)
        now_str = now_utc.isoformat()

        expires_at = None
        if session.duration_type in (DurationType.FIXED.value, DurationType.CUSTOM.value) and session.duration_minutes:
            expires_at = (now_utc + timedelta(minutes=session.duration_minutes)).isoformat()

        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trading_sessions
                SET status = 'RUNNING', started_at = ?, expires_at = ?, last_heartbeat_at = ?
                WHERE id = ?
            """, (now_str, expires_at, now_str, session_id))
            conn.commit()

        updated_session = self.get_session(session_id)

        if bot is not None:
            bot.active_session_id = session_id
            bot.watchlist = list(session.instruments)
            bot.armed_tickers = set(session.instruments)
            bot.is_running = True
            if hasattr(bot, "broker"):
                bot.broker.active_session_id = session_id
            if hasattr(bot, "log_event"):
                bot.log_event(
                    "SESSION",
                    f"Launched Trading Session '{session.name}' [{session.market} | Horizon: {session.horizon} | Capital: {session.currency} {session.allocated_capital:,.2f}].",
                )

        return updated_session

    def pause_session(self, session_id: str, bot: Optional[Any] = None) -> TradingSession:
        """Suspends an active RUNNING session into PAUSED state, freezing countdown."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Session #{session_id} not found")
        if session.status != SessionStatus.RUNNING.value:
            raise ValueError(f"Cannot pause session in state '{session.status}'. Must be in 'RUNNING' state.")

        now_str = datetime.now(timezone.utc).isoformat()
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trading_sessions
                SET status = 'PAUSED', paused_at = ?, last_heartbeat_at = ?
                WHERE id = ?
            """, (now_str, now_str, session_id))
            conn.commit()

        if bot is not None:
            bot.is_running = False
            if hasattr(bot, "log_event"):
                bot.log_event("SESSION", f"Paused Trading Session #{session_id}. Autonomous entries halted; open positions protected.")

        return self.get_session(session_id)

    def resume_session(self, session_id: str, bot: Optional[Any] = None) -> TradingSession:
        """Resumes a PAUSED session, pushing expires_at forward by elapsed pause time."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Session #{session_id} not found")
        if session.status != SessionStatus.PAUSED.value:
            raise ValueError(f"Cannot resume session in state '{session.status}'. Must be in 'PAUSED' state.")

        now_utc = datetime.now(timezone.utc)
        now_str = now_utc.isoformat()

        paused_at_dt = datetime.fromisoformat(session.paused_at) if session.paused_at else now_utc
        if paused_at_dt.tzinfo is None:
            paused_at_dt = paused_at_dt.replace(tzinfo=timezone.utc)
        pause_seconds = max(0, int((now_utc - paused_at_dt).total_seconds()))
        new_accumulated = session.accumulated_pause_seconds + pause_seconds

        new_expires_at = session.expires_at
        if session.expires_at:
            exp_dt = datetime.fromisoformat(session.expires_at)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            new_expires_at = (exp_dt + timedelta(seconds=pause_seconds)).isoformat()

        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trading_sessions
                SET status = 'RUNNING', paused_at = NULL, resumed_at = ?,
                    expires_at = ?, accumulated_pause_seconds = ?, last_heartbeat_at = ?
                WHERE id = ?
            """, (now_str, new_expires_at, new_accumulated, now_str, session_id))
            conn.commit()

        if bot is not None:
            bot.is_running = True
            if hasattr(bot, "log_event"):
                bot.log_event("SESSION", f"Resumed Trading Session #{session_id}. Countdown extended by {pause_seconds}s.")

        return self.get_session(session_id)

    def stop_session(self, session_id: str, bot: Optional[Any] = None, reason: str = "MANUAL_STOP") -> TradingSession:
        """Terminates a session into STOPPED state and executes session_end_policy."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Session #{session_id} not found")
        if session.is_terminal:
            return session

        now_str = datetime.now(timezone.utc).isoformat()
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trading_sessions
                SET status = 'STOPPED', ended_at = ?, last_heartbeat_at = ?
                WHERE id = ?
            """, (now_str, now_str, session_id))
            conn.commit()

        if bot is not None:
            bot.is_running = False
            bot.active_session_id = None
            if hasattr(bot, "broker"):
                bot.broker.active_session_id = None
                if session.session_end_policy == SessionEndPolicy.CLOSE_ALL.value:
                    bot.broker.close_all_positions(getattr(bot, "live_prices", {}), reason=f"SESSION_STOPPED_{reason}")
            if hasattr(bot, "log_event"):
                bot.log_event("SESSION", f"Stopped Trading Session #{session_id} ({reason}). End policy '{session.session_end_policy}' executed.")

        return self.get_session(session_id)

    def check_and_enforce_expiry(
        self, bot: Optional[Any] = None, now_utc: Optional[datetime] = None
    ) -> Optional[TradingSession]:
        """Evaluates active running session on tick; transitions to COMPLETED if expired."""
        session = self.get_active_session()
        if not session or session.status != SessionStatus.RUNNING.value:
            return None
        if session.duration_type == DurationType.MANUAL_STOP.value or not session.expires_at:
            return None

        current_time = now_utc or datetime.now(timezone.utc)
        if not session.is_expired(current_time):
            return None

        now_str = current_time.isoformat()
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trading_sessions
                SET status = 'COMPLETED', ended_at = ?, last_heartbeat_at = ?
                WHERE id = ?
            """, (now_str, now_str, session.id))
            conn.commit()

        if bot is not None:
            bot.is_running = False
            bot.active_session_id = None
            if hasattr(bot, "broker"):
                bot.broker.active_session_id = None
                if session.session_end_policy == SessionEndPolicy.CLOSE_ALL.value:
                    bot.broker.close_all_positions(getattr(bot, "live_prices", {}), reason="SESSION_EXPIRED_CLOSE_ALL")
            if hasattr(bot, "log_event"):
                bot.log_event(
                    "SESSION",
                    f"Session #{session.id} reached expiry at {session.expires_at}. Status: COMPLETED. Policy '{session.session_end_policy}' executed.",
                )

        return self.get_session(session.id)

    def update_session_metrics(self, session_id: str, metrics: Dict[str, Any]) -> None:
        """Updates live financial metrics and heartbeat timestamp for dashboard telemetry."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trading_sessions
                SET current_metrics = ?, last_heartbeat_at = ?
                WHERE id = ?
            """, (json.dumps(metrics), now_str, session_id))
            conn.commit()
```

---

### 4.2 Implementation Blueprint: SQLite Migrations in `src/execution/broker.py`

In `TradingLedgerDB._init_db()` in `src/execution/broker.py`, insert the following block:

```python
            # ----------------- Trading Sessions Table & Indexes ----------------- #
            cursor.execute("""
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
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON trading_sessions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_market ON trading_sessions(market)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_account ON trading_sessions(account_id)")

            # Non-destructive foreign key migrations for existing tables
            for col_sql in [
                "ALTER TABLE orders ADD COLUMN session_id TEXT",
                "ALTER TABLE positions ADD COLUMN session_id TEXT",
                "ALTER TABLE trades ADD COLUMN session_id TEXT",
                "ALTER TABLE equity_history ADD COLUMN session_id TEXT",
            ]:
                try:
                    cursor.execute(col_sql)
                except Exception:
                    pass

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_session ON positions(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_session ON trades(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_equity_history_session ON equity_history(session_id)")
```

And in `PaperBroker.__init__()`:
```python
self.active_session_id: Optional[str] = None
```

---

### 4.3 Unit Test Specification: `tests/test_trading_session_lifecycle.py`

Create `tests/test_trading_session_lifecycle.py` with 10 comprehensive tests validating every lifecycle transition, boundary condition, and database guarantee:

```python
"""Comprehensive Acceptance Tests for Trading Session Lifecycle & SQLite Migrations.

Verifies:
1. TradingSession dataclass instantiation, property calculation, and JSON serialization.
2. Idempotent SQLite migrations in TradingLedgerDB and column existence.
3. Independent backend validation (capital bounds, currency matching, jurisdiction containment).
4. State transitions: CREATED -> RUNNING -> PAUSED -> RUNNING -> STOPPED.
5. Pause time dilation: expires_at extended by pause duration.
6. Automatic expiry enforcement: triggers configured session_end_policy (CLOSE_ALL vs KEEP_OPEN).
7. Single active session constraint per account.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from src.execution.broker import PaperBroker, TradingLedgerDB
from src.execution.session_manager import (
    DurationType,
    SessionEndPolicy,
    SessionManager,
    SessionMarket,
    SessionStatus,
    TradingSession,
)


@pytest.fixture
def temp_ledger(tmp_path: Path):
    """Provides a fresh, isolated TradingLedgerDB in a temporary folder."""
    db_file = tmp_path / "test_session_ledger.db"
    return TradingLedgerDB(db_path=db_file)


@pytest.fixture
def session_manager(temp_ledger: TradingLedgerDB):
    return SessionManager(ledger=temp_ledger)


# 1. Dataclass Serialization & Derived Telemetry
def test_session_dataclass_serialization_and_properties():
    now = datetime.now(timezone.utc)
    exp = (now + timedelta(minutes=60)).isoformat()
    sess = TradingSession(
        id="sess_test1",
        market="US_EQUITIES",
        instruments=["NVDA", "AAPL"],
        horizon="1d",
        duration_type="FIXED",
        duration_minutes=60,
        allocated_capital=25000.0,
        currency="USD",
        status="RUNNING",
        started_at=now.isoformat(),
        expires_at=exp,
    )

    assert sess.is_active is True
    assert sess.is_running is True
    assert sess.is_paused is False
    assert sess.is_terminal is False
    assert sess.is_expired() is False
    assert 3500 <= sess.remaining_seconds() <= 3600

    d = sess.to_dict()
    assert d["id"] == "sess_test1"
    assert d["instruments"] == ["NVDA", "AAPL"]
    assert d["remaining_seconds"] > 0

    reconstructed = TradingSession.from_dict(d)
    assert reconstructed.id == sess.id
    assert reconstructed.instruments == sess.instruments


# 2. SQLite Migration Idempotency & Schema Verification
def test_sqlite_migration_idempotency_and_indexes(temp_ledger: TradingLedgerDB):
    # Verify columns exist
    with temp_ledger._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(trading_sessions)")
        cols = {row["name"] for row in cursor.fetchall()}
        required = {"id", "market", "instruments", "horizon", "duration_type", "duration_minutes",
                    "session_end_policy", "allocated_capital", "currency", "status", "expires_at",
                    "accumulated_pause_seconds", "current_metrics"}
        assert required.issubset(cols)

        # Verify session_id added to execution tables
        for tbl in ["orders", "positions", "trades", "equity_history"]:
            cursor.execute(f"PRAGMA table_info({tbl})")
            tbl_cols = {row["name"] for row in cursor.fetchall()}
            assert "session_id" in tbl_cols, f"session_id missing from {tbl}"

        # Verify indexes exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        idx_names = {row["name"] for row in cursor.fetchall()}
        assert "idx_sessions_status" in idx_names
        assert "idx_sessions_market" in idx_names
        assert "idx_sessions_account" in idx_names

    # Calling _init_db again must succeed without error (strict idempotency)
    temp_ledger._init_db()
    temp_ledger._init_db()


# 3. Independent Parameter Validation
def test_session_manager_validation_rules(session_manager: SessionManager):
    # Valid US session
    session_manager.validate_session_parameters(
        market="US_EQUITIES", currency="USD", instruments=["NVDA", "MSFT"],
        allocated_capital=10000.0, horizon="1d", duration_type="FIXED",
        duration_minutes=60, session_end_policy="CLOSE_ALL"
    )

    # Rejection: Currency mismatch (INR for US market)
    with pytest.raises(ValueError, match="Currency mismatch"):
        session_manager.validate_session_parameters(
            market="US_EQUITIES", currency="INR", instruments=["NVDA"],
            allocated_capital=10000.0, horizon="1d", duration_type="FIXED",
            duration_minutes=60, session_end_policy="CLOSE_ALL"
        )

    # Rejection: Jurisdiction mismatch (Indian stock in US session)
    with pytest.raises(ValueError, match="does not belong to market"):
        session_manager.validate_session_parameters(
            market="US_EQUITIES", currency="USD", instruments=["RELIANCE.NS"],
            allocated_capital=10000.0, horizon="1d", duration_type="FIXED",
            duration_minutes=60, session_end_policy="CLOSE_ALL"
        )

    # Rejection: Non-positive capital
    with pytest.raises(ValueError, match="strictly positive"):
        session_manager.validate_session_parameters(
            market="US_EQUITIES", currency="USD", instruments=["NVDA"],
            allocated_capital=0.0, horizon="1d", duration_type="FIXED",
            duration_minutes=60, session_end_policy="CLOSE_ALL"
        )

    # Rejection: Capital below minimum limit
    with pytest.raises(ValueError, match="outside allowed limits"):
        session_manager.validate_session_parameters(
            market="US_EQUITIES", currency="USD", instruments=["NVDA"],
            allocated_capital=50.0, horizon="1d", duration_type="FIXED",
            duration_minutes=60, session_end_policy="CLOSE_ALL"
        )


# 4. CRUD Operations & Filtering
def test_session_manager_crud_operations(session_manager: SessionManager):
    sess = session_manager.create_session({
        "market": "US_EQUITIES",
        "currency": "USD",
        "instruments": ["NVDA", "AAPL"],
        "allocated_capital": 50000.0,
        "horizon": "1h",
        "duration_type": "FIXED",
        "duration_minutes": 120,
    })
    assert sess.id.startswith("sess_")
    assert sess.status == "CREATED"
    assert sess.allocated_capital == 50000.0

    # Retrieve
    fetched = session_manager.get_session(sess.id)
    assert fetched is not None
    assert fetched.id == sess.id

    # Update in CREATED state
    updated = session_manager.update_session(sess.id, {"name": "Updated Strategy Name", "allocated_capital": 60000.0})
    assert updated.name == "Updated Strategy Name"
    assert updated.allocated_capital == 60000.0

    # List
    listed = session_manager.list_sessions(market="US_EQUITIES")
    assert len(listed) >= 1
    assert any(s.id == sess.id for s in listed)


# 5. Lifecycle Happy Path: CREATED -> RUNNING -> PAUSED -> RUNNING -> STOPPED
def test_session_lifecycle_state_transitions(session_manager: SessionManager):
    sess = session_manager.create_session({
        "market": "US_EQUITIES",
        "currency": "USD",
        "instruments": ["NVDA", "AAPL"],
        "allocated_capital": 50000.0,
        "horizon": "1h",
        "duration_type": "FIXED",
        "duration_minutes": 60,
    })

    # 1. Start
    running = session_manager.start_session(sess.id)
    assert running.status == "RUNNING"
    assert running.started_at is not None
    assert running.expires_at is not None

    # 2. Pause
    paused = session_manager.pause_session(sess.id)
    assert paused.status == "PAUSED"
    assert paused.paused_at is not None

    # 3. Resume
    resumed = session_manager.resume_session(sess.id)
    assert resumed.status == "RUNNING"
    assert resumed.paused_at is None
    assert resumed.resumed_at is not None

    # 4. Stop
    stopped = session_manager.stop_session(sess.id, reason="USER_STOP")
    assert stopped.status == "STOPPED"
    assert stopped.ended_at is not None
    assert stopped.is_terminal is True


# 6. Guard Against Invalid Transitions
def test_session_lifecycle_transition_guards(session_manager: SessionManager):
    sess = session_manager.create_session({
        "market": "US_EQUITIES",
        "currency": "USD",
        "instruments": ["NVDA"],
        "allocated_capital": 10000.0,
        "horizon": "1d",
        "duration_type": "FIXED",
        "duration_minutes": 60,
    })

    # Cannot pause a CREATED session
    with pytest.raises(ValueError, match="Must be in 'RUNNING' state"):
        session_manager.pause_session(sess.id)

    # Cannot resume a CREATED session
    with pytest.raises(ValueError, match="Must be in 'PAUSED' state"):
        session_manager.resume_session(sess.id)

    # Start session
    session_manager.start_session(sess.id)

    # Cannot start an already RUNNING session
    with pytest.raises(ValueError, match="Must be in 'CREATED' state"):
        session_manager.start_session(sess.id)

    # Stop session
    session_manager.stop_session(sess.id)

    # Cannot mutate a STOPPED session
    with pytest.raises(ValueError, match="Cannot update session"):
        session_manager.update_session(sess.id, {"allocated_capital": 20000.0})


# 7. Single Active Session Constraint
def test_single_active_session_constraint(session_manager: SessionManager):
    sess1 = session_manager.create_session({
        "market": "US_EQUITIES", "currency": "USD", "instruments": ["NVDA"],
        "allocated_capital": 10000.0, "horizon": "1d", "duration_type": "MANUAL_STOP"
    })
    sess2 = session_manager.create_session({
        "market": "US_EQUITIES", "currency": "USD", "instruments": ["AAPL"],
        "allocated_capital": 10000.0, "horizon": "1d", "duration_type": "MANUAL_STOP"
    })

    session_manager.start_session(sess1.id)

    # Attempting to start sess2 while sess1 is active must raise RuntimeError
    with pytest.raises(RuntimeError, match="already has active session"):
        session_manager.start_session(sess2.id)

    # Stop sess1, then sess2 can be started cleanly
    session_manager.stop_session(sess1.id)
    session_manager.start_session(sess2.id)
    assert session_manager.get_active_session().id == sess2.id


# 8. Pause Duration Dilation (expires_at Shift)
def test_pause_duration_dilation(session_manager: SessionManager):
    sess = session_manager.create_session({
        "market": "US_EQUITIES", "currency": "USD", "instruments": ["NVDA"],
        "allocated_capital": 10000.0, "horizon": "1d", "duration_type": "FIXED",
        "duration_minutes": 60
    })
    running = session_manager.start_session(sess.id)
    orig_exp = datetime.fromisoformat(running.expires_at)

    session_manager.pause_session(sess.id)

    # Simulate pause duration
    with session_manager.ledger._get_connection() as conn:
        cursor = conn.cursor()
        fake_pause_start = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        cursor.execute("UPDATE trading_sessions SET paused_at = ? WHERE id = ?", (fake_pause_start, sess.id))
        conn.commit()

    resumed = session_manager.resume_session(sess.id)
    new_exp = datetime.fromisoformat(resumed.expires_at)

    # New expires_at must be shifted by ~120s
    diff_sec = (new_exp - orig_exp).total_seconds()
    assert 118 <= diff_sec <= 125
    assert resumed.accumulated_pause_seconds >= 120


# 9. Automatic Expiry & Policy Execution (CLOSE_ALL vs KEEP_OPEN)
def test_session_expiry_enforcement_close_all(session_manager: SessionManager):
    sess = session_manager.create_session({
        "market": "US_EQUITIES", "currency": "USD", "instruments": ["NVDA"],
        "allocated_capital": 10000.0, "horizon": "1d", "duration_type": "FIXED",
        "duration_minutes": 1, "session_end_policy": "CLOSE_ALL"
    })
    session_manager.start_session(sess.id)

    # Mock expired time (10 seconds past expires_at)
    expired_time = datetime.now(timezone.utc) + timedelta(minutes=2)

    # Bot stub to observe policy execution
    class DummyBot:
        def __init__(self):
            self.is_running = True
            self.active_session_id = sess.id
            self.live_prices = {"NVDA": 130.0}
            self.closed_positions = False

            class DummyBroker:
                def __init__(self, outer):
                    self.outer = outer
                    self.active_session_id = sess.id
                def close_all_positions(self, prices, reason=""):
                    self.outer.closed_positions = True
                    return []
            self.broker = DummyBroker(self)
        def log_event(self, lvl, msg):
            pass

    bot = DummyBot()
    completed = session_manager.check_and_enforce_expiry(bot=bot, now_utc=expired_time)
    assert completed is not None
    assert completed.status == "COMPLETED"
    assert completed.ended_at is not None
    assert bot.is_running is False
    assert bot.closed_positions is True


# 10. Live Metrics Update & Heartbeat
def test_session_metrics_update_and_heartbeat(session_manager: SessionManager):
    sess = session_manager.create_session({
        "market": "US_EQUITIES", "currency": "USD", "instruments": ["NVDA"],
        "allocated_capital": 10000.0, "horizon": "1d", "duration_type": "MANUAL_STOP"
    })
    session_manager.start_session(sess.id)

    session_manager.update_session_metrics(sess.id, {
        "current_cash": 8000.0,
        "invested_equity": 2500.0,
        "total_equity": 10500.0,
        "realized_pnl": 500.0,
        "unrealized_pnl": 0.0,
        "total_trades": 2,
        "win_rate_pct": 100.0,
    })

    updated = session_manager.get_session(sess.id)
    assert updated.current_metrics["total_equity"] == 10500.0
    assert updated.current_metrics["realized_pnl"] == 500.0
    assert updated.last_heartbeat_at is not None
```

---

## 5. Verification Method

To independently verify the implementation:

1. **Verify Unit Test Suite Execution**:
   Run the newly implemented test suite using the Windows `py` interpreter:
   ```powershell
   cd C:\Users\Shivam\Desktop\trade_bot
   py -m pytest tests/test_trading_session_lifecycle.py -v
   ```
   *Expected Result*: 10/10 tests pass cleanly without errors.

2. **Verify SQLite Database Schema in Default DB**:
   Query the database using Python:
   ```powershell
   cd C:\Users\Shivam\Desktop\trade_bot
   py -c "from src.execution.broker import TradingLedgerDB; db = TradingLedgerDB(); conn = db._get_connection(); cur = conn.cursor(); cur.execute('PRAGMA table_info(trading_sessions)'); print('Sessions columns:', len(cur.fetchall())); cur.execute('PRAGMA table_info(orders)'); print('Orders session_id:', 'session_id' in [r[1] for r in cur.fetchall()])"
   ```
   *Expected Output*:
   ```
   Sessions columns: 23
   Orders session_id: True
   ```

3. **Verify Zero Regressions Across Existing Platform Tests**:
   ```powershell
   cd C:\Users\Shivam\Desktop\trade_bot
   py -m pytest tests/test_milestone_m2_sessions.py
   py -m pytest tests/test_strategy_horizon_mapper.py
   ```
   *Expected Result*: All existing tests pass with 0 failures.

4. **Conditions for Invalidation**:
   - Any failure where `TradingLedgerDB._init_db()` errors on repeated invocation invalidates the idempotency guarantee.
   - Any failure where `SessionManager.start_session()` allows two sessions to be concurrently `RUNNING` or `PAUSED` on the same account invalidates isolation.
   - Any failure where pausing does not freeze or shifts the expiration timestamp incorrectly invalidates the countdown contract.
