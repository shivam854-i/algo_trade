# Technical Analysis & Architectural Blueprint: Session Model & Database Migrations (Milestone 2 - Part A)

**Module**: SYNAPSE-TITAN Backend Architecture & Session Lifecycle Management  
**Author**: Session Model & SQLite Migration Explorer (`teamwork_explorer`)  
**Target Repository**: `C:\Users\Shivam\Desktop\trade_bot`  
**Working Directory**: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_explorer_1`  
**Date**: 2026-11-05  

---

## 1. Executive Summary

Milestone 2 Part A establishes the persistent foundation for user-controlled paper trading sessions in SYNAPSE-TITAN. Prior to this enhancement, the autonomous execution loop operated as a single monolithic process without user-defined boundaries, capital isolation, duration limits, or portfolio baskets.

This architecture introduces:
1. **`TradingSession` Data Model (`src/execution/session_manager.py`)**: A production-grade dataclass with strict typing, JSON serialization, derived telemetry properties (countdown timer, expiry detection), and an explicit 5-state lifecycle machine (`CREATED`, `RUNNING`, `PAUSED`, `COMPLETED`, `STOPPED`).
2. **SQLite Schema Migrations (`src/execution/broker.py`)**: Fully idempotent migrations adding the `trading_sessions` table with high-performance indexes (`idx_sessions_status`, `idx_sessions_market`, `idx_sessions_account`), and non-destructively adding `session_id TEXT` foreign keys to `orders`, `positions`, `trades`, and `equity_history`.
3. **`SessionManager` Persistence Layer (`src/execution/session_manager.py`)**: A transactional manager handling session creation with independent backend validation, active session isolation, state transitions, pause/resume expiry adjustments, and automatic end-policy enforcement (`CLOSE_ALL` vs `KEEP_OPEN`).

---

## 2. `TradingSession` Data Model & State Machine Design

### 2.1 Lifecycle State Machine

The lifecycle of a trading session follows an explicit finite state machine with strict transition guards:

```
                  ┌────────────────────────┐
                  │        CREATED         │
                  └───────────┬────────────┘
                              │
                    start()   │   stop() / cancel()
                              ▼
                  ┌────────────────────────┐
        ┌────────►│        RUNNING         ├────────┐
        │         └───────┬────────▲───────┘        │
        │                 │        │                │
        │ pause()         │        │ resume()       │ stop()
        │                 ▼        │                │
        │         ┌────────────────┴───────┐        │
        │         │         PAUSED         ├────────┤
        │         └────────────────────────┘        │
        │                                           │
        │ expires_at reached                        │
        ▼                                           ▼
┌───────────────┐                           ┌───────────────┐
│   COMPLETED   │ (Terminal)                │    STOPPED    │ (Terminal)
└───────────────┘                           └───────────────┘
```

#### State Definitions:
- **`CREATED`**: Initial state upon configuration from the setup wizard or API. Parameters are validated, database record is persisted, but the autonomous engine has not yet been armed. Parameters may still be updated in this state.
- **`RUNNING`**: Active trading state. Bot is armed with the approved instrument basket and allocated capital. Expiry countdown is active. New orders and positions can be executed.
- **`PAUSED`**: Temporarily suspended state. Expiry countdown is frozen. No new orders may be placed. Open positions remain monitored for risk/stop-loss. Accumulated pause duration is tracked to extend `expires_at` upon resumption.
- **`COMPLETED`**: Terminal state reached when `now_utc >= expires_at`. Configured `session_end_policy` (`CLOSE_ALL` or `KEEP_OPEN`) has been executed. No further transitions permitted.
- **`STOPPED`**: Terminal state triggered manually via dashboard STOP control, or by catastrophic risk guardrails. Configured `session_end_policy` has been executed. No further transitions permitted.

#### Valid State Transition Matrix:

| From State | Allowed Target States | Trigger Method | Invariant / Side Effect |
|---|---|---|---|
| `CREATED` | `RUNNING` | `start_session()` | Validates no other active session; sets `started_at`, computes `expires_at`; arms bot. |
| `CREATED` | `STOPPED` | `stop_session()` | Aborts session before execution; sets `ended_at`. |
| `RUNNING` | `PAUSED` | `pause_session()` | Sets `paused_at`; halts new bot order generation; preserves open positions. |
| `RUNNING` | `STOPPED` | `stop_session()` | Sets `ended_at`; executes `session_end_policy`; disarms bot. |
| `RUNNING` | `COMPLETED` | `check_and_enforce_expiry()` | Automatically triggered on tick when `now_utc >= expires_at`; executes `session_end_policy`. |
| `PAUSED` | `RUNNING` | `resume_session()` | Sets `resumed_at`; extends `expires_at` by paused duration; unblocks bot order generation. |
| `PAUSED` | `STOPPED` | `stop_session()` | Sets `ended_at`; executes `session_end_policy`; disarms bot. |
| `COMPLETED` | *None* | *None* | Terminal state. Raises `InvalidSessionStateTransitionError`. |
| `STOPPED` | *None* | *None* | Terminal state. Raises `InvalidSessionStateTransitionError`. |

---

### 2.2 Dataclass Schema & Type Definitions

```python
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
import json
import sqlite3
from typing import Any, Dict, List, Optional, Union


class SessionStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"


class DurationType(str, Enum):
    FIXED = "FIXED"
    CUSTOM = "CUSTOM"
    MANUAL_STOP = "MANUAL_STOP"


class SessionEndPolicy(str, Enum):
    CLOSE_ALL = "CLOSE_ALL"
    KEEP_OPEN = "KEEP_OPEN"


class SessionMarket(str, Enum):
    INDIAN_NSE = "INDIAN_NSE"
    US_EQUITIES = "US_EQUITIES"
    CRYPTO = "CRYPTO"
    FOREX = "FOREX"
    COMMODITIES = "COMMODITIES"


class SessionCurrency(str, Enum):
    USD = "USD"
    INR = "INR"


class TradingHorizon(str, Enum):
    ONE_HOUR = "1h"
    ONE_DAY = "1d"
    ONE_WEEK = "1wk"
```

#### Core Dataclass Structure:

```python
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
        """Returns True if the session is currently operational (RUNNING or PAUSED)."""
        return self.status in (SessionStatus.RUNNING.value, SessionStatus.PAUSED.value)

    @property
    def is_running(self) -> bool:
        """Returns True if the session is currently actively trading."""
        return self.status == SessionStatus.RUNNING.value

    @property
    def is_paused(self) -> bool:
        """Returns True if the session is currently suspended."""
        return self.status == SessionStatus.PAUSED.value

    @property
    def is_terminal(self) -> bool:
        """Returns True if the session has reached a final state (COMPLETED or STOPPED)."""
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
        # Filter out computed properties if present
        for key in ["is_active", "is_running", "is_paused", "is_terminal", "is_expired", "remaining_seconds"]:
            clean.pop(key, None)

        # Parse JSON strings if stringified
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
```

---

## 3. SQLite Database Schema Migrations

### 3.1 Migration Strategy in `src/execution/broker.py`

`TradingLedgerDB._init_db()` is called during broker initialization. To guarantee zero data loss and seamless backward compatibility with existing tests and databases:
1. `trading_sessions` table is created via `CREATE TABLE IF NOT EXISTS`.
2. Dedicated single-column indexes are created via `CREATE INDEX IF NOT EXISTS`.
3. Non-destructive `ALTER TABLE` statements add `session_id TEXT` to `orders`, `positions`, `trades`, and `equity_history` inside `try...except Exception: pass` blocks.
4. Fresh `CREATE TABLE IF NOT EXISTS` definitions for `orders`, `positions`, `trades`, and `equity_history` are updated to include `session_id TEXT` natively so that freshly provisioned test databases have the complete schema without relying on alteration.

### 3.2 SQL Table Definition: `trading_sessions`

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

### 3.3 Foreign Key Column Migrations

```python
# Non-destructive addition of session_id foreign keys to execution tables
migration_statements = [
    "ALTER TABLE orders ADD COLUMN session_id TEXT",
    "ALTER TABLE positions ADD COLUMN session_id TEXT",
    "ALTER TABLE trades ADD COLUMN session_id TEXT",
    "ALTER TABLE equity_history ADD COLUMN session_id TEXT",
]
for col_sql in migration_statements:
    try:
        cursor.execute(col_sql)
    except Exception:
        pass

# Indexing session_id across all transactional tables for sub-millisecond query performance
cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(session_id)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_session ON positions(session_id)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_session ON trades(session_id)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_equity_history_session ON equity_history(session_id)")
```

### 3.4 In-Memory / Temporary Database Compatibility
In test fixtures (e.g. `tests/test_gate2_adversarial_order_and_session.py` and `tests/test_milestone_m2_sessions.py`), temporary SQLite databases are initialized on the fly. Because `_init_db()` is completely idempotent, every temporary database automatically gets the updated schema with 0 configuration overhead.

---

## 4. `SessionManager` Persistence Layer Design

### 4.1 Architecture & Method Signatures

The `SessionManager` class encapsulates all transactional queries, status transitions, countdown math, and interaction with the `LiveBotController`.

```python
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
                    # Non-US equity symbol format
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

        # Allowable mutable fields in CREATED
        allowed_fields = ["name", "instruments", "horizon", "duration_minutes", "session_end_policy", "allocated_capital", "strategy_config", "risk_config"]
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

        # Ensure no other session is active on this account
        active = self.get_active_session(session.account_id)
        if active and active.id != session_id:
            raise RuntimeError(
                f"Cannot start session #{session_id}: Account already has active session #{active.id} ({active.status}). "
                "Pause or stop the active session first."
            )

        now_utc = datetime.now(timezone.utc)
        now_str = now_utc.isoformat()

        # Compute expires_at
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

        # Arm LiveBotController if provided
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

        # Calculate pause duration
        paused_at_dt = datetime.fromisoformat(session.paused_at) if session.paused_at else now_utc
        if paused_at_dt.tzinfo is None:
            paused_at_dt = paused_at_dt.replace(tzinfo=timezone.utc)
        pause_seconds = max(0, int((now_utc - paused_at_dt).total_seconds()))
        new_accumulated = session.accumulated_pause_seconds + pause_seconds

        # Shift expires_at forward
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
            return session  # Idempotent on terminal

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

        # Expiry reached! Transition to COMPLETED
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

## 5. Architectural Alignment with Downstream Components

### 5.1 Dynamic Horizon Parameter Binding (M1 HorizonMapper ↔ SessionManager)
When a session is created or started:
```python
from src.strategy.horizon_mapper import HorizonMapper

params = HorizonMapper.get_parameters(session.horizon, market_type="NSE" if session.market == "INDIAN_NSE" else "US")
session.strategy_config = params.to_dict()
```
This binds:
- Bar interval: `5m` for `1h`, `15m` for `1d`, `1d` for `1wk`.
- Feature lookbacks: Scaled window lengths for fractional differentiation and regime HMMs.
- Triple-barrier multipliers: Calibrated profit targets and stop-losses matching holding horizons.

### 5.2 Bot Autonomous Guardrails (`src/execution/live_bot.py`)
In `LiveBotController.step_tick()`:
1. `session_manager.check_and_enforce_expiry(self)` is executed at Step 0 of each tick.
2. If `active_session is None` or `active_session.status != 'RUNNING'`, `self.is_running` is locked to `False`, preventing unapproved trade opens.
3. Candidate stock selection is strictly filtered: `tk in session.instruments`, completely preventing execution outside the approved basket.
4. Capital allocation is bounded by `min(allocated_capital, available_cash)`, preventing capital overallocation.

---

## 6. Conclusion

This design completely addresses R2 and R3 requirements:
- Fully typed, verifiable data model.
- Idempotent and non-destructive SQLite migrations.
- Independent backend parameter validation.
- Pause/resume duration drift compensation.
- Automated end-policy execution without silent extension.
