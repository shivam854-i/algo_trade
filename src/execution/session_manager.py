"""SYNAPSE-TITAN Trading Session Model & Lifecycle Manager.

Manages user-configured paper trading sessions, state transitions,
SQLite persistence, countdown timers, independent validation, and end-policy enforcement.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Union
import uuid

from src.execution.broker import TradingLedgerDB

logger = logging.getLogger("SessionManager")


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
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
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
            p_dt = datetime.fromisoformat(self.paused_at)
            if p_dt.tzinfo is None:
                p_dt = p_dt.replace(tzinfo=timezone.utc)
            exp_dt = datetime.fromisoformat(self.expires_at)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            return max(0, int((exp_dt - p_dt).total_seconds()))

        now = now_utc or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
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

    @staticmethod
    def normalize_market(market: str) -> str:
        """Normalizes market string to canonical SessionMarket value."""
        m = str(market).strip().upper()
        if m in ("US", "NYSE", "NASDAQ", "US_EQUITIES"):
            return SessionMarket.US_EQUITIES.value
        elif m in ("NSE", "NSE_CASH", "INDIAN_NSE", "INDIA"):
            return SessionMarket.INDIAN_NSE.value
        elif m in ("CRYPTO", "CRYPTOCURRENCY"):
            return SessionMarket.CRYPTO.value
        elif m in ("COMMODITY", "COMMODITIES", "CME"):
            return SessionMarket.COMMODITIES.value
        elif m in ("FOREX", "FX"):
            return SessionMarket.FOREX.value
        return m

    @staticmethod
    def normalize_horizon(horizon: str) -> str:
        """Normalizes horizon string to standard short format (1h, 1d, 1wk)."""
        h = str(horizon).strip().lower().replace("_", " ").replace("-", " ")
        if h in ("1h", "1 hour", "1hour", "intraday", "hourly"):
            return "1h"
        elif h in ("1d", "1 day", "1day", "daily", "eod"):
            return "1d"
        elif h in ("1wk", "1w", "1 week", "1week", "swing", "weekly"):
            return "1wk"
        return h

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
        canonical_market = self.normalize_market(market)
        valid_markets = [m.value for m in SessionMarket]
        if canonical_market not in valid_markets:
            raise ValueError(f"Unsupported market: '{market}'. Must be one of {valid_markets}")

        # 2. Currency validation matching market
        expected_currency = "INR" if canonical_market == SessionMarket.INDIAN_NSE.value else "USD"
        if currency.upper() != expected_currency:
            raise ValueError(
                f"Currency mismatch: Market '{canonical_market}' requires currency '{expected_currency}', got '{currency}'"
            )

        # 3. Capital validation
        if allocated_capital is None:
            raise ValueError("Allocated capital cannot be None")
        try:
            cap_val = float(allocated_capital)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid allocated capital: {allocated_capital}")

        if cap_val <= 0:
            raise ValueError(f"Allocated capital must be strictly positive, got {cap_val}")

        min_cap = 1000.0
        max_cap = 10_000_000.0
        if not (min_cap <= cap_val <= max_cap):
            raise ValueError(
                f"Allocated capital {cap_val:,.2f} outside allowed limits [{min_cap:,.0f}, {max_cap:,.0f}] {currency}"
            )

        # 4. Instrument list validation
        if not instruments or not isinstance(instruments, list):
            raise ValueError("Instruments must be a non-empty list of ticker symbols")
        unique_tickers = list(dict.fromkeys([str(t).upper().strip() for t in instruments if str(t).strip()]))
        if not unique_tickers:
            raise ValueError("Instruments basket must contain at least one valid ticker symbol")
        if len(unique_tickers) > 20:
            raise ValueError(f"Instruments basket exceeds maximum limit of 20 symbols (got {len(unique_tickers)})")

        # 5. Jurisdiction containment check
        for tk in unique_tickers:
            if canonical_market == SessionMarket.INDIAN_NSE.value:
                if not (tk.endswith(".NS") or tk.endswith(".BO")):
                    raise ValueError(f"Ticker '{tk}' does not belong to market {canonical_market} (expected .NS or .BO suffix)")
            elif canonical_market == SessionMarket.CRYPTO.value:
                if not (tk.endswith("-USD") or tk.endswith("-USDT")):
                    raise ValueError(f"Ticker '{tk}' does not belong to market {canonical_market} (expected -USD or -USDT suffix)")
            elif canonical_market == SessionMarket.COMMODITIES.value:
                if not (tk.endswith("=F") or tk in ("GLD", "SLV", "USO", "UNG")):
                    raise ValueError(f"Ticker '{tk}' does not belong to market {canonical_market} (expected =F suffix)")
            elif canonical_market == SessionMarket.FOREX.value:
                if not (tk.endswith("=X") or tk in ("DX-Y.NYB", "UUP")):
                    raise ValueError(f"Ticker '{tk}' does not belong to market {canonical_market} (expected =X suffix)")
            elif canonical_market == SessionMarket.US_EQUITIES.value:
                if "." in tk or "=" in tk or "-" in tk:
                    raise ValueError(f"Ticker '{tk}' does not belong to market {canonical_market}")

        # 6. Horizon validation
        norm_h = self.normalize_horizon(horizon)
        if norm_h not in [h.value for h in TradingHorizon]:
            raise ValueError(f"Invalid horizon: '{horizon}'. Must be one of {[h.value for h in TradingHorizon]}")

        # 7. Duration validation
        dt = str(duration_type).upper()
        if dt not in [d.value for d in DurationType]:
            raise ValueError(f"Invalid duration_type: '{duration_type}'. Must be one of {[d.value for d in DurationType]}")
        if dt in (DurationType.FIXED.value, DurationType.CUSTOM.value):
            if duration_minutes is None or int(duration_minutes) <= 0:
                raise ValueError(f"duration_minutes must be a positive integer for duration_type '{dt}'")
            if int(duration_minutes) > 10080:
                raise ValueError("duration_minutes exceeds maximum allowable duration of 10,080 minutes (1 week)")

        # 8. End policy validation
        pol = str(session_end_policy).upper()
        if pol not in [p.value for p in SessionEndPolicy]:
            raise ValueError(f"Invalid session_end_policy: '{session_end_policy}'. Must be one of {[p.value for p in SessionEndPolicy]}")

    # ----------------- CRUD Operations ----------------- #

    def create_session(self, data: Union[Dict[str, Any], Any]) -> TradingSession:
        """Validates configuration, generates session ID, and creates an SQLite record in CREATED state."""
        if hasattr(data, "model_dump"):
            raw = data.model_dump()
        elif hasattr(data, "dict"):
            raw = data.dict()
        else:
            raw = dict(data)

        market = self.normalize_market(raw.get("market", ""))
        currency = str(raw.get("currency", "USD")).upper()
        instruments = raw.get("instruments", [])
        allocated_capital = float(raw.get("allocated_capital", 0.0))
        horizon = self.normalize_horizon(raw.get("horizon", "1d"))
        duration_type = str(raw.get("duration_type", "FIXED")).upper()
        duration_minutes = raw.get("duration_minutes")
        if duration_minutes is not None:
            duration_minutes = int(duration_minutes)
        session_end_policy = str(raw.get("session_end_policy", "CLOSE_ALL")).upper()

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
        user_id = str(raw.get("user_id", "DEFAULT_USER"))
        account_id = str(raw.get("account_id", "PAPER_DEFAULT"))
        name = raw.get("name") or f"{market} {horizon} Session"

        strategy_cfg = raw.get("strategy_config") or {}
        risk_cfg = raw.get("risk_config") or {}
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

        session = self.get_session(session_id)
        if session is None:
            raise RuntimeError(f"Failed to retrieve created session #{session_id}")
        return session

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
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status.upper())
        if market:
            query += " AND market = ?"
            params.append(self.normalize_market(market))
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

    def update_session(self, session_id: str, updates: Union[Dict[str, Any], Any]) -> TradingSession:
        """Updates parameters of a session in CREATED or PAUSED state."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Session #{session_id} not found")
        if session.status not in (SessionStatus.CREATED.value, SessionStatus.PAUSED.value):
            raise ValueError(f"Cannot update session #{session_id} while in state '{session.status}'")

        if hasattr(updates, "model_dump"):
            raw = updates.model_dump(exclude_unset=True)
        elif hasattr(updates, "dict"):
            raw = {k: v for k, v in updates.dict().items() if v is not None}
        else:
            raw = dict(updates)

        allowed_fields = [
            "name", "instruments", "horizon", "duration_type", "duration_minutes",
            "session_end_policy", "allocated_capital", "strategy_config", "risk_config"
        ]
        set_clauses = []
        params = []
        for k in allowed_fields:
            if k in raw and raw[k] is not None:
                val = raw[k]
                if k == "horizon":
                    val = self.normalize_horizon(val)
                elif k in ("instruments", "strategy_config", "risk_config") and not isinstance(val, str):
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

        updated = self.get_session(session_id)
        if updated is None:
            raise RuntimeError(f"Failed to reload session #{session_id} after update")
        return updated

    # ----------------- Lifecycle State Machine Actions ----------------- #

    def start_session(self, session_id: str, bot: Optional[Any] = None) -> TradingSession:
        """Launches a CREATED session into RUNNING state, calculating expires_at and arming the bot."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Session #{session_id} not found")
        if session.status != SessionStatus.CREATED.value:
            raise ValueError(f"Cannot start session in state '{session.status}'. Must be in 'CREATED' state.")

        now_utc = datetime.now(timezone.utc)
        now_str = now_utc.isoformat()

        expires_at = None
        if session.duration_type in (DurationType.FIXED.value, DurationType.CUSTOM.value) and session.duration_minutes:
            expires_at = (now_utc + timedelta(minutes=session.duration_minutes)).isoformat()

        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("""
                SELECT id, status FROM trading_sessions
                WHERE account_id = ? AND status IN ('RUNNING', 'PAUSED')
                LIMIT 1
            """, (session.account_id,))
            active_row = cursor.fetchone()
            if active_row and active_row["id"] != session_id:
                conn.rollback()
                raise RuntimeError(
                    f"Cannot start session #{session_id}: Account already has active session #{active_row['id']} ({active_row['status']}). "
                    "Pause or stop the active session first."
                )

            cursor.execute("""
                UPDATE trading_sessions
                SET status = 'RUNNING', started_at = ?, expires_at = ?, last_heartbeat_at = ?
                WHERE id = ? AND status = 'CREATED'
            """, (now_str, expires_at, now_str, session_id))
            if cursor.rowcount == 0:
                conn.rollback()
                raise ValueError(f"Cannot start session #{session_id}. Session might not be in CREATED state.")
            conn.commit()

        updated_session = self.get_session(session_id)
        if updated_session is None:
            raise RuntimeError(f"Failed to reload session #{session_id} after start")

        if bot is not None:
            bot.active_session_id = session_id
            bot.watchlist = list(updated_session.instruments)
            bot.armed_tickers = set(updated_session.instruments)
            bot.is_running = True
            if hasattr(bot, "broker"):
                bot.broker.active_session_id = session_id
            if hasattr(bot, "bind_horizon_parameters"):
                bot.bind_horizon_parameters(updated_session.horizon, market_type=updated_session.market)
            if hasattr(bot, "log_event"):
                bot.log_event(
                    "SESSION",
                    f"Launched Trading Session '{updated_session.name}' [{updated_session.market} | Horizon: {updated_session.horizon} | Capital: {updated_session.currency} {updated_session.allocated_capital:,.2f}].",
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

        updated = self.get_session(session_id)
        if updated is None:
            raise RuntimeError(f"Failed to reload session #{session_id} after pause")
        return updated

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

        updated = self.get_session(session_id)
        if updated is None:
            raise RuntimeError(f"Failed to reload session #{session_id} after resume")
        return updated

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
                    live_prices = getattr(bot, "live_prices", {})
                    bot.broker.close_all_positions(live_prices, reason=f"SESSION_STOPPED_{reason}")
            if hasattr(bot, "log_event"):
                bot.log_event("SESSION", f"Stopped Trading Session #{session_id} ({reason}). End policy '{session.session_end_policy}' executed.")

        updated = self.get_session(session_id)
        if updated is None:
            raise RuntimeError(f"Failed to reload session #{session_id} after stop")
        return updated

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
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

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
                    live_prices = getattr(bot, "live_prices", {})
                    bot.broker.close_all_positions(live_prices, reason="SESSION_EXPIRED_CLOSE_ALL")
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

    def compute_session_performance(self, session_id: str, bot: Optional[Any] = None) -> Dict[str, Any]:
        """Computes comprehensive session performance KPIs and returns metrics dictionary."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Session #{session_id} not found")

        # Query closed trades for this session strictly
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE session_id = ?", (session_id,))
            closed_trades = cursor.fetchall()

            cursor.execute("SELECT * FROM positions WHERE status = 'OPEN' AND session_id = ?", (session_id,))
            open_positions = cursor.fetchall()

        total_trades = len(closed_trades)
        winning_trades = sum(1 for t in closed_trades if float(t["net_pnl"]) > 0)
        losing_trades = sum(1 for t in closed_trades if float(t["net_pnl"]) < 0)
        realized_pnl = sum(float(t["net_pnl"]) for t in closed_trades)

        gross_profit = sum(float(t["net_pnl"]) for t in closed_trades if float(t["net_pnl"]) > 0)
        gross_loss = abs(sum(float(t["net_pnl"]) for t in closed_trades if float(t["net_pnl"]) < 0))

        if gross_loss > 0:
            profit_factor = round(gross_profit / gross_loss, 2)
        elif gross_profit > 0:
            profit_factor = 999.99
        else:
            profit_factor = 1.0

        win_rate_pct = round((winning_trades / total_trades) * 100.0, 1) if total_trades > 0 else 0.0

        # Invested and unrealized PnL from open positions
        invested_equity = 0.0
        unrealized_pnl = 0.0
        for p in open_positions:
            alloc = float(p["allocated_capital"])
            invested_equity += alloc
            last_p = float(p["last_price"]) if p["last_price"] else float(p["entry_price"])
            entry_p = float(p["entry_price"])
            shares = float(p["shares"])
            if p["direction"] == "LONG":
                unrealized_pnl += (last_p - entry_p) * shares
            else:
                unrealized_pnl += (entry_p - last_p) * shares

        initial_cap = float(session.allocated_capital)
        current_cash = max(0.0, initial_cap + realized_pnl - invested_equity)
        total_equity = current_cash + invested_equity + unrealized_pnl
        net_pnl = realized_pnl + unrealized_pnl
        return_pct = round((net_pnl / initial_cap) * 100.0, 2) if initial_cap > 0 else 0.0

        metrics = {
            "session_id": session.id,
            "name": session.name,
            "status": session.status,
            "market": session.market,
            "currency": session.currency,
            "horizon": session.horizon,
            "duration_type": session.duration_type,
            "duration_minutes": session.duration_minutes,
            "allocated_capital": initial_cap,
            "starting_capital": initial_cap,
            "current_cash": round(current_cash, 2),
            "invested_equity": round(invested_equity, 2),
            "total_equity": round(total_equity, 2),
            "net_pnl": round(net_pnl, 2),
            "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "return_pct": return_pct,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate_pct": win_rate_pct,
            "profit_factor": profit_factor,
            "open_positions_count": len(open_positions),
            "is_active": session.is_active,
            "is_running": session.is_running,
            "is_expired": session.is_expired(),
            "remaining_seconds": session.remaining_seconds(),
            "accumulated_pause_seconds": session.accumulated_pause_seconds,
            "session_end_policy": session.session_end_policy,
        }
        return metrics
