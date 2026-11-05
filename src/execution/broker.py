"""Autonomous Live Paper-Trading & Broker Execution Engine.

Provides persistent, real-time virtual order routing, position tracking,
bid/ask + slippage simulation, and Mark-to-Market PnL audit logs backed by SQLite.

CRITICAL SAFETY INVARIANT:
This module operates strictly in PAPER_TRADING_ONLY mode with virtual capital.
All external real-money brokerage order submission adapters are permanently
isolated and hard-disabled.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from src.execution.frictions import FrictionEvaluator

logger = logging.getLogger(__name__)

# Hard architectural safety invariant: Real-money order execution is strictly forbidden.
PAPER_TRADING_ONLY: bool = True


@dataclass
class Position:
    id: int
    ticker: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    shares: float
    allocated_capital: float
    target_price: float
    stop_price: float
    entry_time: str
    holding_bars: int
    status: str  # "OPEN" or "CLOSED"
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_return_pct: float = 0.0
    bid_price: float = 0.0
    ask_price: float = 0.0
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    entry_fee: float = 0.0
    market_timestamp: str = ""
    session_id: Optional[str] = None


@dataclass
class TradeLog:
    id: int
    ticker: str
    direction: str
    entry_price: float
    exit_price: float
    shares: float
    gross_pnl: float
    friction_fee: float
    net_pnl: float
    return_pct: float
    entry_time: str
    exit_time: str
    exit_reason: str
    slippage_cost: float = 0.0
    commission_fee: float = 0.0
    market_timestamp: str = ""
    session_id: Optional[str] = None


class TradingLedgerDB:
    """SQLite-backed persistent ledger for virtual accounts, positions, orders, and trades."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self.db_path = base_dir / "data" / "trading_ledger.db"
        else:
            self.db_path = Path(db_path)

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes tables for accounts, open positions, orders, equity history, and closed trades."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Account state
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    account_type TEXT NOT NULL,
                    initial_capital REAL NOT NULL,
                    current_cash REAL NOT NULL,
                    realized_pnl REAL DEFAULT 0.0,
                    peak_equity REAL DEFAULT 100000.0,
                    max_drawdown_pct REAL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            for col_sql in [
                "ALTER TABLE accounts ADD COLUMN peak_equity REAL DEFAULT 100000.0",
                "ALTER TABLE accounts ADD COLUMN max_drawdown_pct REAL DEFAULT 0.0",
            ]:
                try:
                    cursor.execute(col_sql)
                except Exception:
                    pass

            # Open / Active Virtual Positions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    shares REAL NOT NULL,
                    allocated_capital REAL NOT NULL,
                    target_price REAL NOT NULL,
                    stop_price REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    holding_bars INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'OPEN',
                    last_price REAL DEFAULT 0.0,
                    bid_price REAL DEFAULT 0.0,
                    ask_price REAL DEFAULT 0.0,
                    spread_bps REAL DEFAULT 0.0,
                    slippage_bps REAL DEFAULT 0.0,
                    entry_fee REAL DEFAULT 0.0,
                    market_timestamp TEXT DEFAULT ''
                )
            """)
            for col_sql in [
                "ALTER TABLE positions ADD COLUMN last_price REAL DEFAULT 0.0",
                "ALTER TABLE positions ADD COLUMN bid_price REAL DEFAULT 0.0",
                "ALTER TABLE positions ADD COLUMN ask_price REAL DEFAULT 0.0",
                "ALTER TABLE positions ADD COLUMN spread_bps REAL DEFAULT 0.0",
                "ALTER TABLE positions ADD COLUMN slippage_bps REAL DEFAULT 0.0",
                "ALTER TABLE positions ADD COLUMN entry_fee REAL DEFAULT 0.0",
                "ALTER TABLE positions ADD COLUMN market_timestamp TEXT DEFAULT ''",
            ]:
                try:
                    cursor.execute(col_sql)
                except Exception:
                    pass

            # Historical Closed Virtual Trades
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    shares REAL NOT NULL,
                    gross_pnl REAL NOT NULL,
                    friction_fee REAL NOT NULL,
                    net_pnl REAL NOT NULL,
                    return_pct REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT NOT NULL,
                    exit_reason TEXT NOT NULL,
                    slippage_cost REAL DEFAULT 0.0,
                    commission_fee REAL DEFAULT 0.0,
                    market_timestamp TEXT DEFAULT ''
                )
            """)
            for col_sql in [
                "ALTER TABLE trades ADD COLUMN slippage_cost REAL DEFAULT 0.0",
                "ALTER TABLE trades ADD COLUMN commission_fee REAL DEFAULT 0.0",
                "ALTER TABLE trades ADD COLUMN market_timestamp TEXT DEFAULT ''",
            ]:
                try:
                    cursor.execute(col_sql)
                except Exception:
                    pass

            # Virtual Orders (Pre-market pending, working limit, partially filled, filled, rejected, cancelled)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT,
                    account_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    order_type TEXT DEFAULT 'MARKET',
                    shares REAL NOT NULL,
                    price REAL,
                    limit_price REAL DEFAULT 0.0,
                    filled_shares REAL DEFAULT 0.0,
                    remaining_shares REAL DEFAULT 0.0,
                    allocated_capital REAL NOT NULL,
                    target_price REAL NOT NULL,
                    stop_price REAL NOT NULL,
                    submitted_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    fill_price REAL DEFAULT 0.0,
                    bid_price REAL DEFAULT 0.0,
                    ask_price REAL DEFAULT 0.0,
                    slippage_bps REAL DEFAULT 0.0,
                    fee_paid REAL DEFAULT 0.0,
                    market_timestamp TEXT DEFAULT '',
                    filled_at TEXT,
                    executed_at TEXT,
                    cancellation_reason TEXT,
                    rejection_reason TEXT
                )
            """)
            for col_sql in [
                "ALTER TABLE orders ADD COLUMN limit_price REAL DEFAULT 0.0",
                "ALTER TABLE orders ADD COLUMN filled_shares REAL DEFAULT 0.0",
                "ALTER TABLE orders ADD COLUMN remaining_shares REAL DEFAULT 0.0",
                "ALTER TABLE orders ADD COLUMN bid_price REAL DEFAULT 0.0",
                "ALTER TABLE orders ADD COLUMN ask_price REAL DEFAULT 0.0",
                "ALTER TABLE orders ADD COLUMN slippage_bps REAL DEFAULT 0.0",
                "ALTER TABLE orders ADD COLUMN fee_paid REAL DEFAULT 0.0",
                "ALTER TABLE orders ADD COLUMN market_timestamp TEXT DEFAULT ''",
                "ALTER TABLE orders ADD COLUMN rejection_reason TEXT",
            ]:
                try:
                    cursor.execute(col_sql)
                except Exception:
                    pass

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_ticker ON orders(ticker)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_account ON orders(account_id)")

            # Equity & Drawdown Audit Trail
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS equity_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    total_equity REAL NOT NULL,
                    cash REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    exposure_pct REAL NOT NULL,
                    drawdown_pct REAL NOT NULL
                )
            """)

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

            # Ensure default paper account exists
            cursor.execute("SELECT id FROM accounts WHERE id = 'PAPER_DEFAULT'")
            if not cursor.fetchone():
                now_str = datetime.now(timezone.utc).isoformat()
                cursor.execute("""
                    INSERT INTO accounts (
                        id, account_type, initial_capital, current_cash, realized_pnl,
                        peak_equity, max_drawdown_pct, created_at, updated_at
                    )
                    VALUES ('PAPER_DEFAULT', 'PAPER', 100000.0, 100000.0, 0.0, 100000.0, 0.0, ?, ?)
                """, (now_str, now_str))

            conn.commit()


class BaseBrokerAdapter:
    """Isolated broker adapter interface.

    CRITICAL SAFETY LOCK: Real brokerage order submission is permanently disabled
    in SYNAPSE-TITAN. All orders must execute exclusively in the local SQLite PaperBroker.
    """

    def submit_order(self, ticker: str, direction: str, shares: float, price: float) -> bool:
        raise PermissionError(
            "CRITICAL SAFETY LOCK: Real brokerage order submission is permanently disabled "
            "in the SYNAPSE-TITAN paper-trading system."
        )

    def get_market_price(self, ticker: str) -> float:
        raise NotImplementedError


class AlpacaBrokerAdapter(BaseBrokerAdapter):
    """Isolated adapter stub — real brokerage order routing is hard-disabled."""

    def __init__(self, api_key: str = "", secret_key: str = "", paper: bool = True):
        if not paper:
            raise PermissionError("Live brokerage mode is strictly forbidden in SYNAPSE-TITAN.")
        self.api_key = ""
        self.secret_key = ""
        self.paper = True
        self.base_url = "PAPER_LOCAL_SQLITE_ONLY"

    def submit_order(self, ticker: str, direction: str, shares: float, price: float) -> bool:
        raise PermissionError(
            "CRITICAL SAFETY LOCK: External brokerage order submission is disabled. Use PaperBroker."
        )


class ZerodhaKiteAdapter(BaseBrokerAdapter):
    """Isolated adapter stub — real brokerage order routing is hard-disabled."""

    def __init__(self, api_key: str = "", access_token: str = ""):
        self.api_key = ""
        self.access_token = ""

    def submit_order(self, ticker: str, direction: str, shares: float, price: float) -> bool:
        raise PermissionError(
            "CRITICAL SAFETY LOCK: External brokerage order submission is disabled. Use PaperBroker."
        )


class MT5BrokerAdapter(BaseBrokerAdapter):
    """Isolated adapter stub — real brokerage order routing is hard-disabled."""

    def __init__(self, login: int = 0, server: str = "", password: str = ""):
        self.login = 0
        self.server = ""
        self.password = ""

    def submit_order(self, ticker: str, direction: str, shares: float, price: float) -> bool:
        raise PermissionError(
            "CRITICAL SAFETY LOCK: External brokerage order submission is disabled. Use PaperBroker."
        )


class PaperBroker:
    """Autonomous Paper-Trading Engine with bid/ask spreads, slippage, frictions, and mark-to-market tracking."""

    def __init__(
        self,
        account_id: str = "PAPER_DEFAULT",
        initial_capital: float = 100000.0,
        db_path: Optional[Path] = None,
        max_concurrent_positions: int = 5,
        max_position_exposure_pct: float = 25.0,
        max_portfolio_exposure_pct: float = 85.0,
    ):
        self.account_id = account_id
        self.max_concurrent_positions = max_concurrent_positions
        self.max_position_exposure_pct = max_position_exposure_pct
        self.max_portfolio_exposure_pct = max_portfolio_exposure_pct
        self.active_session_id: Optional[str] = None
        self.ledger = TradingLedgerDB(db_path=db_path)
        self._ensure_account(initial_capital)

    def _ensure_account(self, capital: float):
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM accounts WHERE id = ?", (self.account_id,))
            if not cursor.fetchone():
                now_str = datetime.now(timezone.utc).isoformat()
                cursor.execute("""
                    INSERT INTO accounts (
                        id, account_type, initial_capital, current_cash, realized_pnl,
                        peak_equity, max_drawdown_pct, created_at, updated_at
                    )
                    VALUES (?, 'PAPER', ?, ?, 0.0, ?, 0.0, ?, ?)
                """, (self.account_id, capital, capital, capital, now_str, now_str))
                conn.commit()

    @staticmethod
    def compute_realistic_fill_price(
        ticker: str,
        direction: str,
        is_entry: bool,
        reference_price: float,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        order_shares: float = 10.0,
        avg_daily_volume: float = 2_000_000.0,
        daily_volatility: float = 0.02,
        apply_slippage: bool = True,
    ) -> Tuple[float, float, float, float]:
        """Computes realistic Bid/Ask + Almgren-Chriss slippage fill price.

        Returns:
            (fill_price, effective_bid, effective_ask, slippage_bps)
        """
        profile = FrictionEvaluator.get_profile(ticker)
        spread_bps_val = float(getattr(profile, "bid_ask_spread_bps", getattr(profile, "spread_bps", 2.0)))
        half_spread_dec = (spread_bps_val / 10000.0) / 2.0

        if bid_price is not None and ask_price is not None and bid_price > 0 and ask_price > 0:
            eff_bid = float(bid_price)
            eff_ask = max(float(ask_price), eff_bid)
        elif bid_price is not None and bid_price > 0:
            eff_bid = float(bid_price)
            eff_ask = eff_bid * (1.0 + 2.0 * half_spread_dec)
        elif ask_price is not None and ask_price > 0:
            eff_ask = float(ask_price)
            eff_bid = eff_ask * (1.0 - 2.0 * half_spread_dec)
        else:
            eff_bid = float(reference_price) * (1.0 - half_spread_dec)
            eff_ask = float(reference_price) * (1.0 + half_spread_dec)

        if apply_slippage:
            raw_impact = FrictionEvaluator.compute_almgren_chriss_slippage_bps(
                ticker=ticker,
                order_notional=max(100.0, float(order_shares) * float(reference_price)),
                daily_dollar_volume=max(1e6, float(avg_daily_volume) * float(reference_price)),
                annualized_vol=max(0.05, float(daily_volatility) * np.sqrt(252.0)),
            ) / 2.0
            slippage_bps = float(np.clip(raw_impact, 0.5, 50.0))
        else:
            slippage_bps = 0.0

        slip_dec = slippage_bps / 10000.0

        # LONG entry or SHORT exit buys at the Ask + positive slippage
        is_buy_action = (direction.upper() == "LONG" and is_entry) or (
            direction.upper() == "SHORT" and not is_entry
        )
        if is_buy_action:
            fill_price = eff_ask * (1.0 + slip_dec)
        else:
            # LONG exit or SHORT entry sells at the Bid - negative slippage
            fill_price = eff_bid * (1.0 - slip_dec)

        return round(fill_price, 6), round(eff_bid, 6), round(eff_ask, 6), round(slippage_bps, 2)

    def get_account_summary(self) -> Dict[str, Union[float, int, str, bool]]:
        """Computes live virtual account metrics: Cash, Exposure, Total Equity, Realized/Unrealized PnL, Drawdown."""
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM accounts WHERE id = ?", (self.account_id,))
            acc = cursor.fetchone()
            if not acc:
                return {}

            cash = float(acc["current_cash"])
            realized_pnl = float(acc["realized_pnl"])
            initial_cap = float(acc["initial_capital"])
            peak_equity = float(acc["peak_equity"]) if ("peak_equity" in acc.keys() and acc["peak_equity"]) else initial_cap
            stored_max_dd = float(acc["max_drawdown_pct"]) if ("max_drawdown_pct" in acc.keys() and acc["max_drawdown_pct"]) else 0.0

            cursor.execute("""
                SELECT COALESCE(SUM(allocated_capital), 0.0) as reserved
                FROM orders
                WHERE account_id = ? AND status IN ('PRE_MARKET_PENDING', 'WORKING')
            """, (self.account_id,))
            res_row = cursor.fetchone()
            reserved_cash = float(res_row["reserved"]) if res_row else 0.0

            cursor.execute("""
                SELECT COALESCE(SUM(friction_fee), 0.0) as trade_fees
                FROM trades
                WHERE account_id = ?
            """, (self.account_id,))
            fee_row = cursor.fetchone()
            closed_fees = float(fee_row["trade_fees"]) if fee_row else 0.0

        positions = self.get_open_positions()
        allocated_capital = sum(p.allocated_capital for p in positions)
        unrealized_pnl = sum(p.unrealized_pnl for p in positions)
        open_fees = sum(p.entry_fee for p in positions)
        total_equity = cash + allocated_capital + unrealized_pnl
        total_return_pct = ((total_equity - initial_cap) / initial_cap) * 100.0 if initial_cap > 0 else 0.0
        available_cash = max(0.0, cash - reserved_cash)

        exposure_notional = sum(abs(p.shares * (p.current_price if p.current_price > 0 else p.entry_price)) for p in positions)
        exposure_pct = (exposure_notional / total_equity * 100.0) if total_equity > 0 else 0.0

        # Update peak equity and max drawdown
        new_peak = max(peak_equity, initial_cap, total_equity)
        current_dd = ((new_peak - total_equity) / new_peak * 100.0) if new_peak > 0 else 0.0
        max_dd = max(stored_max_dd, current_dd)

        if new_peak > peak_equity or max_dd > stored_max_dd:
            with self.ledger._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE accounts SET peak_equity = ?, max_drawdown_pct = ? WHERE id = ?",
                    (new_peak, max_dd, self.account_id),
                )
                conn.commit()

        return {
            "account_id": self.account_id,
            "account_mode": "VIRTUAL_PAPER",
            "paper_trading_only": True,
            "initial_capital": round(initial_cap, 2),
            "cash": round(available_cash, 2),
            "current_cash": round(cash, 2),
            "reserved_cash": round(reserved_cash, 2),
            "available_cash": round(available_cash, 2),
            "allocated_capital": round(allocated_capital, 2),
            "exposure_notional": round(exposure_notional, 2),
            "exposure_pct": round(exposure_pct, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "realized_pnl": round(realized_pnl, 2),
            "total_equity": round(total_equity, 2),
            "total_return_pct": round(total_return_pct, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "current_drawdown_pct": round(current_dd, 2),
            "total_transaction_costs": round(closed_fees + open_fees, 2),
            "open_positions_count": len(positions),
        }

    def get_open_positions(self) -> List[Position]:
        """Retrieves all currently open virtual positions."""
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM positions WHERE account_id = ? AND status = 'OPEN' ORDER BY id DESC
            """, (self.account_id,))
            rows = cursor.fetchall()

        positions = []
        for r in rows:
            keys = r.keys()
            entry_p = float(r["entry_price"])
            last_p = float(r["last_price"]) if ("last_price" in keys and r["last_price"] and float(r["last_price"]) > 0) else entry_p
            shares = float(r["shares"])
            alloc_cap = float(r["allocated_capital"])
            direction = r["direction"]
            if direction == "LONG":
                u_pnl = shares * (last_p - entry_p)
            else:
                u_pnl = shares * (entry_p - last_p)
            u_ret = (u_pnl / alloc_cap * 100.0) if alloc_cap > 0 else 0.0

            pos = Position(
                id=r["id"],
                ticker=r["ticker"],
                direction=direction,
                entry_price=entry_p,
                shares=shares,
                allocated_capital=alloc_cap,
                target_price=float(r["target_price"]),
                stop_price=float(r["stop_price"]),
                entry_time=r["entry_time"],
                holding_bars=r["holding_bars"],
                status=r["status"],
                current_price=last_p,
                unrealized_pnl=round(u_pnl, 2),
                unrealized_return_pct=round(u_ret, 2),
                bid_price=float(r["bid_price"]) if ("bid_price" in keys and r["bid_price"]) else 0.0,
                ask_price=float(r["ask_price"]) if ("ask_price" in keys and r["ask_price"]) else 0.0,
                spread_bps=float(r["spread_bps"]) if ("spread_bps" in keys and r["spread_bps"]) else 0.0,
                slippage_bps=float(r["slippage_bps"]) if ("slippage_bps" in keys and r["slippage_bps"]) else 0.0,
                entry_fee=float(r["entry_fee"]) if ("entry_fee" in keys and r["entry_fee"]) else 0.0,
                market_timestamp=str(r["market_timestamp"]) if ("market_timestamp" in keys and r["market_timestamp"]) else "",
                session_id=str(r["session_id"]) if ("session_id" in keys and r["session_id"]) else None,
            )
            positions.append(pos)
        return positions

    def has_duplicate_order_or_position(self, ticker: str, direction: Optional[str] = None) -> bool:
        """Checks if an active position or pending/working order already exists for `ticker`."""
        tk = ticker.upper()
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            if direction:
                cursor.execute(
                    "SELECT COUNT(*) as cnt FROM positions WHERE account_id = ? AND ticker = ? AND direction = ? AND status = 'OPEN'",
                    (self.account_id, tk, direction.upper()),
                )
            else:
                cursor.execute(
                    "SELECT COUNT(*) as cnt FROM positions WHERE account_id = ? AND ticker = ? AND status = 'OPEN'",
                    (self.account_id, tk),
                )
            if int(cursor.fetchone()["cnt"]) > 0:
                return True

            if direction:
                cursor.execute(
                    """
                    SELECT COUNT(*) as cnt FROM orders
                    WHERE account_id = ? AND ticker = ? AND direction = ?
                      AND status IN ('PRE_MARKET_PENDING', 'WORKING', 'PARTIALLY_FILLED')
                    """,
                    (self.account_id, tk, direction.upper()),
                )
            else:
                cursor.execute(
                    """
                    SELECT COUNT(*) as cnt FROM orders
                    WHERE account_id = ? AND ticker = ?
                      AND status IN ('PRE_MARKET_PENDING', 'WORKING', 'PARTIALLY_FILLED')
                    """,
                    (self.account_id, tk),
                )
            return int(cursor.fetchone()["cnt"]) > 0

    def _record_order_event(
        self,
        ticker: str,
        direction: str,
        order_type: str,
        shares: float,
        price: float,
        allocated_capital: float,
        target_price: float,
        stop_price: float,
        status: str,
        limit_price: float = 0.0,
        filled_shares: float = 0.0,
        remaining_shares: float = 0.0,
        fill_price: float = 0.0,
        bid_price: float = 0.0,
        ask_price: float = 0.0,
        slippage_bps: float = 0.0,
        fee_paid: float = 0.0,
        market_timestamp: str = "",
        rejection_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        filled_at = now_str if status in ("FILLED", "PARTIALLY_FILLED") else None
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO orders (
                    account_id, ticker, direction, order_type, shares, price, limit_price,
                    filled_shares, remaining_shares, allocated_capital, target_price, stop_price,
                    submitted_at, created_at, status, fill_price, bid_price, ask_price,
                    slippage_bps, fee_paid, market_timestamp, filled_at, executed_at, rejection_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.account_id,
                ticker.upper(),
                direction.upper(),
                order_type.upper(),
                float(shares),
                float(price) if price and not math.isnan(price) else 0.0,
                float(limit_price),
                float(filled_shares),
                float(remaining_shares),
                float(allocated_capital),
                float(target_price),
                float(stop_price),
                now_str,
                now_str,
                status,
                float(fill_price),
                float(bid_price),
                float(ask_price),
                float(slippage_bps),
                float(fee_paid),
                str(market_timestamp or now_str),
                filled_at,
                filled_at,
                rejection_reason,
            ))
            order_num = cursor.lastrowid
            order_id_str = f"ORD-{order_num}"
            cursor.execute("UPDATE orders SET order_id = ? WHERE id = ?", (order_id_str, order_num))
            conn.commit()

        return {
            "id": order_num,
            "order_id": order_id_str,
            "account_id": self.account_id,
            "ticker": ticker.upper(),
            "direction": direction.upper(),
            "order_type": order_type.upper(),
            "shares": round(float(shares), 6),
            "price": round(float(price), 4) if price and not math.isnan(price) else 0.0,
            "limit_price": round(float(limit_price), 4),
            "filled_shares": round(float(filled_shares), 6),
            "remaining_shares": round(float(remaining_shares), 6),
            "allocated_capital": round(float(allocated_capital), 2),
            "target_price": round(float(target_price), 4),
            "stop_price": round(float(stop_price), 4),
            "status": status,
            "fill_price": round(float(fill_price), 4),
            "bid_price": round(float(bid_price), 4),
            "ask_price": round(float(ask_price), 4),
            "slippage_bps": round(float(slippage_bps), 2),
            "fee_paid": round(float(fee_paid), 2),
            "market_timestamp": str(market_timestamp or now_str),
            "submitted_at": now_str,
            "filled_at": filled_at,
            "rejection_reason": rejection_reason,
        }

    def open_position(
        self,
        ticker: str,
        direction: str,  # "LONG" or "SHORT"
        current_price: float,
        target_price: float,
        stop_price: float,
        allocation_weight_pct: float = 10.0,
        custom_allocated_capital: Optional[float] = None,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        use_bid_ask: bool = False,
        apply_slippage: bool = False,
        is_stale: bool = False,
        market_open: bool = True,
        market_timestamp: Optional[str] = None,
        check_duplicate: bool = False,
        enforce_exposure_limits: bool = False,
        session_id: Optional[str] = None,
    ) -> Optional[Position]:
        """Executes a new virtual position, deducting cash and recording entry prices and fees."""
        ticker = ticker.upper()
        direction = direction.upper()

        # Guard against unavailable / invalid / NaN prices
        if current_price is None or math.isnan(float(current_price)) or float(current_price) <= 0.0:
            logger.warning(f"Rejected position open on {ticker}: unavailable or invalid price ({current_price})")
            return None

        if is_stale:
            logger.warning(f"Rejected position open on {ticker}: market quote is STALE.")
            return None

        if not market_open:
            logger.warning(f"Rejected position open on {ticker}: exchange session is CLOSED.")
            return None

        if check_duplicate and self.has_duplicate_order_or_position(ticker, direction):
            logger.warning(f"Rejected duplicate position open on {ticker} ({direction}).")
            return None

        summary = self.get_account_summary()
        cash = float(summary.get("current_cash", 0.0))
        total_equity = float(summary.get("total_equity", 100000.0))
        open_count = int(summary.get("open_positions_count", 0))
        current_exposure_pct = float(summary.get("exposure_pct", 0.0))

        if enforce_exposure_limits:
            if open_count >= self.max_concurrent_positions:
                logger.warning(
                    f"Rejected position open on {ticker}: max concurrent positions ({self.max_concurrent_positions}) reached."
                )
                return None
            if current_exposure_pct >= self.max_portfolio_exposure_pct:
                logger.warning(
                    f"Rejected position open on {ticker}: portfolio exposure ({current_exposure_pct:.1f}%) exceeds limit ({self.max_portfolio_exposure_pct:.1f}%)."
                )
                return None

        # Capital to allocate
        if custom_allocated_capital is not None and custom_allocated_capital > 0:
            alloc_cap = min(float(custom_allocated_capital), cash)
        else:
            capped_weight = (
                min(float(allocation_weight_pct), self.max_position_exposure_pct)
                if enforce_exposure_limits
                else float(allocation_weight_pct)
            )
            target_alloc = total_equity * (capped_weight / 100.0)
            alloc_cap = min(target_alloc, cash)

        if enforce_exposure_limits and total_equity > 0:
            max_pos_dollars = total_equity * (self.max_position_exposure_pct / 100.0)
            remaining_portfolio_dollars = max(
                0.0,
                total_equity * (self.max_portfolio_exposure_pct / 100.0) - float(summary.get("exposure_notional", 0.0)),
            )
            alloc_cap = min(alloc_cap, max_pos_dollars, remaining_portfolio_dollars)

        if alloc_cap < 50.0:
            logger.warning(f"Insufficient cash or exposure capacity (${alloc_cap:.2f}) to open position on {ticker}")
            return None

        approx_shares = alloc_cap / float(current_price)
        fill_p, eff_bid, eff_ask, slip_bps = self.compute_realistic_fill_price(
            ticker=ticker,
            direction=direction,
            is_entry=True,
            reference_price=float(current_price),
            bid_price=bid_price,
            ask_price=ask_price,
            order_shares=approx_shares,
            apply_slippage=apply_slippage or use_bid_ask,
        )

        # If caller explicitly passed bid/ask or requested realistic bid/ask fill, use fill_p;
        # otherwise preserve exact scalar current_price for backward compatibility with legacy tests.
        effective_entry_price = fill_p if (use_bid_ask or bid_price is not None or ask_price is not None or apply_slippage) else float(current_price)
        mid_p = (eff_bid + eff_ask) / 2.0 if (eff_bid + eff_ask) > 0 else effective_entry_price
        spread_bps = ((eff_ask - eff_bid) / mid_p * 10000.0) if mid_p > 0 else 0.0

        # Friction deduction on entry
        friction_dec = FrictionEvaluator.calculate_round_trip_friction_bps(ticker) / 10000.0 / 2.0
        entry_fee = alloc_cap * friction_dec
        net_alloc = alloc_cap - entry_fee
        shares = net_alloc / effective_entry_price

        now_str = datetime.now(timezone.utc).isoformat()
        mkt_ts = str(market_timestamp or now_str)
        effective_session_id = session_id or getattr(self, "active_session_id", None)

        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO positions (
                    account_id, ticker, direction, entry_price, shares, allocated_capital,
                    target_price, stop_price, entry_time, holding_bars, status, last_price,
                    bid_price, ask_price, spread_bps, slippage_bps, entry_fee, market_timestamp,
                    session_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.account_id,
                ticker,
                direction,
                effective_entry_price,
                shares,
                alloc_cap,
                float(target_price),
                float(stop_price),
                now_str,
                effective_entry_price,
                eff_bid,
                eff_ask,
                round(spread_bps, 2),
                round(slip_bps, 2),
                round(entry_fee, 4),
                mkt_ts,
                effective_session_id,
            ))
            pos_id = cursor.lastrowid

            # Deduct cash from account
            new_cash = cash - alloc_cap
            cursor.execute("""
                UPDATE accounts SET current_cash = ?, updated_at = ? WHERE id = ?
            """, (new_cash, now_str, self.account_id))
            conn.commit()

        logger.info(
            f"✅ [PAPER] Opened {direction} position on {ticker} | {shares:.4f} shares @ {effective_entry_price:.4f} "
            f"(Bid: {eff_bid:.2f}, Ask: {eff_ask:.2f}, Slip: {slip_bps:.1f}bps, Fee: ${entry_fee:.2f}, Alloc: ${alloc_cap:.2f})"
        )

        return Position(
            id=pos_id,
            ticker=ticker,
            direction=direction,
            entry_price=effective_entry_price,
            shares=shares,
            allocated_capital=alloc_cap,
            target_price=float(target_price),
            stop_price=float(stop_price),
            entry_time=now_str,
            holding_bars=0,
            status="OPEN",
            current_price=effective_entry_price,
            unrealized_pnl=0.0,
            unrealized_return_pct=0.0,
            bid_price=eff_bid,
            ask_price=eff_ask,
            spread_bps=round(spread_bps, 2),
            slippage_bps=round(slip_bps, 2),
            entry_fee=round(entry_fee, 2),
            market_timestamp=mkt_ts,
            session_id=effective_session_id,
        )

    def submit_order(
        self,
        ticker: str,
        direction: str,
        current_price: float,
        target_price: float,
        stop_price: float,
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
        allocation_weight_pct: float = 10.0,
        custom_allocated_capital: Optional[float] = None,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        available_liquidity_shares: Optional[float] = None,
        is_stale: bool = False,
        market_open: bool = True,
        market_timestamp: Optional[str] = None,
        prevent_duplicates: bool = True,
        enforce_exposure_limits: bool = True,
    ) -> Dict[str, Any]:
        """Submits a virtual MARKET or LIMIT order with full validation, bid/ask fills, and partial-fill support."""
        ticker = ticker.upper()
        direction = direction.upper()
        order_type = order_type.upper()

        # 1. Unavailable / Invalid price check
        if current_price is None or math.isnan(float(current_price)) or float(current_price) <= 0.0:
            return self._record_order_event(
                ticker=ticker,
                direction=direction,
                order_type=order_type,
                shares=0.0,
                price=0.0,
                allocated_capital=0.0,
                target_price=target_price,
                stop_price=stop_price,
                status="REJECTED",
                limit_price=limit_price or 0.0,
                market_timestamp=market_timestamp or "",
                rejection_reason="INVALID_OR_UNAVAILABLE_PRICE",
            )

        # 2. Stale market data check
        if is_stale:
            return self._record_order_event(
                ticker=ticker,
                direction=direction,
                order_type=order_type,
                shares=0.0,
                price=current_price,
                allocated_capital=0.0,
                target_price=target_price,
                stop_price=stop_price,
                status="REJECTED",
                limit_price=limit_price or 0.0,
                market_timestamp=market_timestamp or "",
                rejection_reason="STALE_MARKET_DATA",
            )

        # 3. Permitted market hours check
        if not market_open:
            return self._record_order_event(
                ticker=ticker,
                direction=direction,
                order_type=order_type,
                shares=0.0,
                price=current_price,
                allocated_capital=0.0,
                target_price=target_price,
                stop_price=stop_price,
                status="REJECTED",
                limit_price=limit_price or 0.0,
                market_timestamp=market_timestamp or "",
                rejection_reason="OUTSIDE_MARKET_HOURS",
            )

        # 4. Duplicate order / position protection
        if prevent_duplicates and self.has_duplicate_order_or_position(ticker, direction):
            return self._record_order_event(
                ticker=ticker,
                direction=direction,
                order_type=order_type,
                shares=0.0,
                price=current_price,
                allocated_capital=0.0,
                target_price=target_price,
                stop_price=stop_price,
                status="REJECTED",
                limit_price=limit_price or 0.0,
                market_timestamp=market_timestamp or "",
                rejection_reason="DUPLICATE_ORDER_OR_POSITION",
            )

        summary = self.get_account_summary()
        available_cash = float(summary.get("available_cash", 0.0))
        total_equity = float(summary.get("total_equity", 100000.0))
        open_count = int(summary.get("open_positions_count", 0))
        current_exposure_pct = float(summary.get("exposure_pct", 0.0))

        # 5. Concurrent position & exposure limits
        if enforce_exposure_limits:
            if open_count >= self.max_concurrent_positions:
                return self._record_order_event(
                    ticker=ticker,
                    direction=direction,
                    order_type=order_type,
                    shares=0.0,
                    price=current_price,
                    allocated_capital=0.0,
                    target_price=target_price,
                    stop_price=stop_price,
                    status="REJECTED",
                    limit_price=limit_price or 0.0,
                    market_timestamp=market_timestamp or "",
                    rejection_reason="MAX_CONCURRENT_POSITIONS_EXCEEDED",
                )
            if current_exposure_pct >= self.max_portfolio_exposure_pct:
                return self._record_order_event(
                    ticker=ticker,
                    direction=direction,
                    order_type=order_type,
                    shares=0.0,
                    price=current_price,
                    allocated_capital=0.0,
                    target_price=target_price,
                    stop_price=stop_price,
                    status="REJECTED",
                    limit_price=limit_price or 0.0,
                    market_timestamp=market_timestamp or "",
                    rejection_reason="MAX_PORTFOLIO_EXPOSURE_EXCEEDED",
                )

        # Determine allocation
        if custom_allocated_capital is not None and custom_allocated_capital > 0:
            alloc_cap = min(float(custom_allocated_capital), available_cash)
        else:
            capped_w = (
                min(float(allocation_weight_pct), self.max_position_exposure_pct)
                if enforce_exposure_limits
                else float(allocation_weight_pct)
            )
            alloc_cap = min(total_equity * (capped_w / 100.0), available_cash)

        if enforce_exposure_limits and total_equity > 0:
            max_pos_cap = total_equity * (self.max_position_exposure_pct / 100.0)
            rem_port_cap = max(
                0.0,
                total_equity * (self.max_portfolio_exposure_pct / 100.0) - float(summary.get("exposure_notional", 0.0)),
            )
            alloc_cap = min(alloc_cap, max_pos_cap, rem_port_cap)

        if alloc_cap < 50.0:
            return self._record_order_event(
                ticker=ticker,
                direction=direction,
                order_type=order_type,
                shares=0.0,
                price=current_price,
                allocated_capital=0.0,
                target_price=target_price,
                stop_price=stop_price,
                status="REJECTED",
                limit_price=limit_price or 0.0,
                market_timestamp=market_timestamp or "",
                rejection_reason="INSUFFICIENT_CAPITAL_OR_EXPOSURE_LIMIT",
            )

        desired_shares = alloc_cap / float(current_price)
        fill_p, eff_bid, eff_ask, slip_bps = self.compute_realistic_fill_price(
            ticker=ticker,
            direction=direction,
            is_entry=True,
            reference_price=float(current_price),
            bid_price=bid_price,
            ask_price=ask_price,
            order_shares=desired_shares,
            apply_slippage=True,
        )

        # 6. Limit order handling
        if order_type == "LIMIT":
            if limit_price is None or float(limit_price) <= 0.0:
                return self._record_order_event(
                    ticker=ticker,
                    direction=direction,
                    order_type=order_type,
                    shares=desired_shares,
                    price=current_price,
                    allocated_capital=alloc_cap,
                    target_price=target_price,
                    stop_price=stop_price,
                    status="REJECTED",
                    limit_price=0.0,
                    market_timestamp=market_timestamp or "",
                    rejection_reason="INVALID_LIMIT_PRICE",
                )
            lim_p = float(limit_price)
            is_marketable = (direction == "LONG" and eff_ask <= lim_p) or (
                direction == "SHORT" and eff_bid >= lim_p
            )
            if not is_marketable:
                return self._record_order_event(
                    ticker=ticker,
                    direction=direction,
                    order_type="LIMIT",
                    shares=desired_shares,
                    price=current_price,
                    allocated_capital=alloc_cap,
                    target_price=target_price,
                    stop_price=stop_price,
                    status="WORKING",
                    limit_price=lim_p,
                    filled_shares=0.0,
                    remaining_shares=desired_shares,
                    bid_price=eff_bid,
                    ask_price=eff_ask,
                    market_timestamp=market_timestamp or "",
                )
            # Marketable limit fills at no worse than limit_price
            if direction == "LONG":
                fill_p = min(fill_p, lim_p)
            else:
                fill_p = max(fill_p, lim_p)

        # 7. Partial fill check against available top-of-book liquidity
        fill_fraction = 1.0
        if available_liquidity_shares is not None and float(available_liquidity_shares) > 0:
            if float(available_liquidity_shares) < desired_shares:
                fill_fraction = float(available_liquidity_shares) / desired_shares

        filled_alloc = alloc_cap * fill_fraction
        pos = self.open_position(
            ticker=ticker,
            direction=direction,
            current_price=fill_p,
            target_price=target_price,
            stop_price=stop_price,
            allocation_weight_pct=0.0,
            custom_allocated_capital=filled_alloc,
            bid_price=eff_bid,
            ask_price=eff_ask,
            use_bid_ask=False,  # fill_p already incorporates bid/ask + slippage
            apply_slippage=False,
            is_stale=False,
            market_open=True,
            market_timestamp=market_timestamp,
            check_duplicate=False,
            enforce_exposure_limits=False,
        )
        if not pos:
            return self._record_order_event(
                ticker=ticker,
                direction=direction,
                order_type=order_type,
                shares=desired_shares,
                price=current_price,
                allocated_capital=alloc_cap,
                target_price=target_price,
                stop_price=stop_price,
                status="REJECTED",
                limit_price=limit_price or 0.0,
                market_timestamp=market_timestamp or "",
                rejection_reason="EXECUTION_FAILED",
            )

        status = "PARTIALLY_FILLED" if fill_fraction < 0.9999 else "FILLED"
        rem_shares = max(0.0, desired_shares - pos.shares) if status == "PARTIALLY_FILLED" else 0.0
        order_dict = self._record_order_event(
            ticker=ticker,
            direction=direction,
            order_type=order_type,
            shares=desired_shares,
            price=current_price,
            allocated_capital=filled_alloc,
            target_price=target_price,
            stop_price=stop_price,
            status=status,
            limit_price=limit_price or 0.0,
            filled_shares=pos.shares,
            remaining_shares=rem_shares,
            fill_price=pos.entry_price,
            bid_price=eff_bid,
            ask_price=eff_ask,
            slippage_bps=slip_bps,
            fee_paid=pos.entry_fee,
            market_timestamp=market_timestamp or pos.entry_time,
        )
        order_dict["position_id"] = pos.id
        return order_dict

    def evaluate_working_orders(self, quotes: Dict[str, Any]) -> List[Position]:
        """Evaluates WORKING limit orders against incoming market quotes and fills marketable orders."""
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM orders
                WHERE account_id = ? AND status = 'WORKING'
                ORDER BY id ASC
            """, (self.account_id,))
            working = cursor.fetchall()

        filled_positions: List[Position] = []
        for row in working:
            tk = row["ticker"]
            if tk not in quotes:
                continue
            q = quotes[tk]
            if isinstance(q, (int, float)):
                last_p = float(q)
                bid_p, ask_p = last_p, last_p
                is_stale = False
            elif isinstance(q, dict):
                last_p = float(q.get("last", q.get("last_price", 0.0)))
                bid_p = float(q.get("bid", q.get("bid_price", last_p)))
                ask_p = float(q.get("ask", q.get("ask_price", last_p)))
                is_stale = bool(q.get("is_stale", False))
            else:
                last_p = float(getattr(q, "last_price", 0.0))
                bid_p = float(getattr(q, "bid_price", last_p))
                ask_p = float(getattr(q, "ask_price", last_p))
                is_stale = bool(getattr(q, "is_stale", False))

            if is_stale or last_p <= 0:
                continue

            direction = row["direction"]
            lim_p = float(row["limit_price"])
            alloc_cap = float(row["allocated_capital"])
            target_p = float(row["target_price"])
            stop_p = float(row["stop_price"])

            is_marketable = (direction == "LONG" and ask_p <= lim_p) or (
                direction == "SHORT" and bid_p >= lim_p
            )
            if not is_marketable:
                continue

            exec_p = min(ask_p, lim_p) if direction == "LONG" else max(bid_p, lim_p)
            pos = self.open_position(
                ticker=tk,
                direction=direction,
                current_price=exec_p,
                target_price=target_p,
                stop_price=stop_p,
                allocation_weight_pct=0.0,
                custom_allocated_capital=alloc_cap,
                bid_price=bid_p,
                ask_price=ask_p,
                use_bid_ask=False,
            )
            if pos:
                now_str = datetime.now(timezone.utc).isoformat()
                with self.ledger._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE orders
                        SET status = 'FILLED', fill_price = ?, filled_shares = ?, remaining_shares = 0.0,
                            bid_price = ?, ask_price = ?, fee_paid = ?, filled_at = ?, executed_at = ?
                        WHERE id = ?
                    """, (pos.entry_price, pos.shares, bid_p, ask_p, pos.entry_fee, now_str, now_str, row["id"]))
                    conn.commit()
                filled_positions.append(pos)
        return filled_positions

    def close_position(
        self,
        position_id: int,
        exit_price: float,
        exit_reason: str = "MANUAL_CLOSE",
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        use_bid_ask: bool = False,
        market_timestamp: Optional[str] = None,
    ) -> Optional[TradeLog]:
        """Closes an open virtual position, books realized PnL, deducts exit friction, and releases cash."""
        if exit_price is None or math.isnan(float(exit_price)) or float(exit_price) <= 0.0:
            logger.warning(f"Rejected close_position #{position_id}: invalid exit_price ({exit_price})")
            return None

        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM positions WHERE id = ? AND status = 'OPEN'", (position_id,))
            row = cursor.fetchone()
            if not row:
                return None

            direction = row["direction"]
            entry_price = float(row["entry_price"])
            shares = float(row["shares"])
            alloc_cap = float(row["allocated_capital"])
            entry_time = row["entry_time"]
            ticker = row["ticker"]

            fill_exit_p, eff_bid, eff_ask, slip_bps = self.compute_realistic_fill_price(
                ticker=ticker,
                direction=direction,
                is_entry=False,
                reference_price=float(exit_price),
                bid_price=bid_price,
                ask_price=ask_price,
                order_shares=shares,
                apply_slippage=use_bid_ask,
            )
            effective_exit_price = fill_exit_p if use_bid_ask else float(exit_price)

            # Calculate returns & fees
            if direction == "LONG":
                gross_ret = (effective_exit_price - entry_price) / entry_price
            else:
                gross_ret = (entry_price - effective_exit_price) / entry_price

            friction_dec = FrictionEvaluator.calculate_round_trip_friction_bps(ticker) / 10000.0
            total_fee = (shares * entry_price) * friction_dec
            slippage_dollars = (shares * effective_exit_price) * (slip_bps / 10000.0)
            gross_pnl = shares * entry_price * gross_ret
            net_pnl = gross_pnl - total_fee
            return_pct = (net_pnl / alloc_cap) * 100.0 if alloc_cap > 0 else 0.0

            returned_capital = alloc_cap + net_pnl
            now_str = datetime.now(timezone.utc).isoformat()
            mkt_ts = str(market_timestamp or now_str)

            # 1. Update position status to CLOSED
            cursor.execute(
                "UPDATE positions SET status = 'CLOSED', last_price = ? WHERE id = ?",
                (effective_exit_price, position_id),
            )

            session_id_val = str(row["session_id"]) if ("session_id" in row.keys() and row["session_id"]) else getattr(self, "active_session_id", None)

            # 2. Record completed trade
            cursor.execute("""
                INSERT INTO trades (
                    account_id, ticker, direction, entry_price, exit_price, shares,
                    gross_pnl, friction_fee, net_pnl, return_pct, entry_time, exit_time,
                    exit_reason, slippage_cost, commission_fee, market_timestamp, session_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.account_id,
                ticker,
                direction,
                entry_price,
                effective_exit_price,
                shares,
                gross_pnl,
                total_fee,
                net_pnl,
                return_pct,
                entry_time,
                now_str,
                exit_reason,
                round(slippage_dollars, 4),
                round(total_fee, 4),
                mkt_ts,
                session_id_val,
            ))
            trade_id = cursor.lastrowid

            # 3. Release capital back to account
            cursor.execute("SELECT current_cash, realized_pnl FROM accounts WHERE id = ?", (self.account_id,))
            acc_row = cursor.fetchone()
            new_cash = float(acc_row["current_cash"]) + returned_capital
            new_realized = float(acc_row["realized_pnl"]) + net_pnl

            cursor.execute("""
                UPDATE accounts SET current_cash = ?, realized_pnl = ?, updated_at = ? WHERE id = ?
            """, (new_cash, new_realized, now_str, self.account_id))

            conn.commit()

        logger.info(
            f"🎯 [PAPER] Closed {direction} on {ticker} | Exit: {effective_exit_price:.4f} | "
            f"Net PnL: ${net_pnl:+.2f} ({return_pct:+.2f}%) | Reason: {exit_reason}"
        )

        return TradeLog(
            id=trade_id,
            ticker=ticker,
            direction=direction,
            entry_price=round(entry_price, 4),
            exit_price=round(effective_exit_price, 4),
            shares=round(shares, 4),
            gross_pnl=round(gross_pnl, 2),
            friction_fee=round(total_fee, 2),
            net_pnl=round(net_pnl, 2),
            return_pct=round(return_pct, 2),
            entry_time=entry_time,
            exit_time=now_str,
            exit_reason=exit_reason,
            slippage_cost=round(slippage_dollars, 2),
            commission_fee=round(total_fee, 2),
            market_timestamp=mkt_ts,
            session_id=session_id_val,
        )

    def update_and_audit_positions(
        self, current_prices: Dict[str, Any]
    ) -> Tuple[List[Position], List[TradeLog]]:
        """Inspects all open virtual positions against incoming genuine market prices/quotes/candles.

        Enforces:
        - Bid/Ask-aware exit valuation where Bid/Ask quotes are supplied.
        - Gap-aware Stop-Loss execution (if market opens or gaps past stop_price, fills at the worse gapped price).
        - Conservative intrabar conflict resolution (if both Stop-Loss and Take-Profit are crossed in one bar,
          STOP_LOSS strictly takes precedence).
        """
        open_positions = self.get_open_positions()
        updated_positions: List[Position] = []
        closed_trades: List[TradeLog] = []

        for pos in open_positions:
            if pos.ticker not in current_prices:
                updated_positions.append(pos)
                continue

            raw_val = current_prices[pos.ticker]
            bid_p: Optional[float] = None
            ask_p: Optional[float] = None
            open_p: Optional[float] = None
            high_p: Optional[float] = None
            low_p: Optional[float] = None
            mkt_ts: str = ""

            if isinstance(raw_val, (int, float)):
                curr_price = float(raw_val)
            elif isinstance(raw_val, dict):
                curr_price = float(raw_val.get("last", raw_val.get("last_price", pos.current_price or pos.entry_price)))
                bid_p = float(raw_val["bid"]) if "bid" in raw_val and raw_val["bid"] else (
                    float(raw_val["bid_price"]) if "bid_price" in raw_val and raw_val["bid_price"] else None
                )
                ask_p = float(raw_val["ask"]) if "ask" in raw_val and raw_val["ask"] else (
                    float(raw_val["ask_price"]) if "ask_price" in raw_val and raw_val["ask_price"] else None
                )
                open_p = float(raw_val["open"]) if "open" in raw_val and raw_val["open"] else (
                    float(raw_val["day_open"]) if "day_open" in raw_val and raw_val["day_open"] else None
                )
                high_p = float(raw_val["high"]) if "high" in raw_val and raw_val["high"] else (
                    float(raw_val["day_high"]) if "day_high" in raw_val and raw_val["day_high"] else None
                )
                low_p = float(raw_val["low"]) if "low" in raw_val and raw_val["low"] else (
                    float(raw_val["day_low"]) if "day_low" in raw_val and raw_val["day_low"] else None
                )
                mkt_ts = str(raw_val.get("timestamp_utc", raw_val.get("market_timestamp", "")))
            else:
                curr_price = float(getattr(raw_val, "last_price", pos.current_price or pos.entry_price))
                bid_p = float(getattr(raw_val, "bid_price", 0.0)) or None
                ask_p = float(getattr(raw_val, "ask_price", 0.0)) or None
                open_p = float(getattr(raw_val, "day_open", 0.0)) or None
                high_p = float(getattr(raw_val, "day_high", 0.0)) or None
                low_p = float(getattr(raw_val, "day_low", 0.0)) or None
                mkt_ts = str(getattr(raw_val, "timestamp_utc", ""))

            if math.isnan(curr_price) or curr_price <= 0.0:
                updated_positions.append(pos)
                continue

            # Exit reference price: LONG exits at Bid (if available), SHORT exits at Ask (if available)
            if pos.direction == "LONG":
                mtm_price = bid_p if (bid_p is not None and bid_p > 0) else curr_price
            else:
                mtm_price = ask_p if (ask_p is not None and ask_p > 0) else curr_price

            bar_open = open_p if (open_p is not None and open_p > 0) else mtm_price
            bar_high = max(high_p, mtm_price, bar_open) if (high_p is not None and high_p > 0) else max(mtm_price, bar_open)
            bar_low = min(low_p, mtm_price, bar_open) if (low_p is not None and low_p > 0) else min(mtm_price, bar_open)

            pos.current_price = mtm_price
            if bid_p is not None and bid_p > 0:
                pos.bid_price = bid_p
            if ask_p is not None and ask_p > 0:
                pos.ask_price = ask_p
            pos.holding_bars += 1

            # Unrealized calculation
            if pos.direction == "LONG":
                raw_pnl = pos.shares * (mtm_price - pos.entry_price)
            else:
                raw_pnl = pos.shares * (pos.entry_price - mtm_price)

            pos.unrealized_pnl = round(raw_pnl, 2)
            pos.unrealized_return_pct = round((raw_pnl / pos.allocated_capital) * 100.0, 2) if pos.allocated_capital > 0 else 0.0

            # Check dynamic barriers with conservative intrabar SL/TP priority & gap-aware stop fills
            exit_reason: Optional[str] = None
            exec_exit_price: float = mtm_price

            if pos.direction == "LONG":
                sl_crossed = (bar_low <= pos.stop_price) or (mtm_price <= pos.stop_price)
                tp_crossed = (bar_high >= pos.target_price) or (mtm_price >= pos.target_price)

                if sl_crossed and tp_crossed:
                    # Conservative rule: when both SL and TP are crossed in the same candle, STOP_LOSS wins
                    exit_reason = "STOP_LOSS"
                    exec_exit_price = min(bar_open, pos.stop_price) if bar_open < pos.stop_price else pos.stop_price
                elif sl_crossed:
                    exit_reason = "STOP_LOSS"
                    # Gap-aware stop loss: if market opened or ticked below stop_price, fill at the worse gapped price
                    if bar_open < pos.stop_price or mtm_price < pos.stop_price:
                        exec_exit_price = min(bar_open, mtm_price, pos.stop_price)
                    else:
                        exec_exit_price = pos.stop_price
                elif tp_crossed:
                    exit_reason = "PROFIT_TARGET"
                    exec_exit_price = mtm_price if mtm_price >= pos.target_price else pos.target_price

            elif pos.direction == "SHORT":
                sl_crossed = (bar_high >= pos.stop_price) or (mtm_price >= pos.stop_price)
                tp_crossed = (bar_low <= pos.target_price) or (mtm_price <= pos.target_price)

                if sl_crossed and tp_crossed:
                    exit_reason = "STOP_LOSS"
                    exec_exit_price = max(bar_open, pos.stop_price) if bar_open > pos.stop_price else pos.stop_price
                elif sl_crossed:
                    exit_reason = "STOP_LOSS"
                    # Gap-aware stop loss for SHORT: if market opened or ticked above stop_price, fill at worse higher price
                    if bar_open > pos.stop_price or mtm_price > pos.stop_price:
                        exec_exit_price = max(bar_open, mtm_price, pos.stop_price)
                    else:
                        exec_exit_price = pos.stop_price
                elif tp_crossed:
                    exit_reason = "PROFIT_TARGET"
                    exec_exit_price = mtm_price if mtm_price <= pos.target_price else pos.target_price

            if exit_reason:
                trade = self.close_position(
                    pos.id,
                    exec_exit_price,
                    exit_reason,
                    bid_price=bid_p,
                    ask_price=ask_p,
                    use_bid_ask=False,
                    market_timestamp=mkt_ts,
                )
                if trade:
                    closed_trades.append(trade)
            else:
                with self.ledger._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE positions
                        SET holding_bars = ?, last_price = ?, bid_price = COALESCE(?, bid_price),
                            ask_price = COALESCE(?, ask_price), market_timestamp = COALESCE(?, market_timestamp)
                        WHERE id = ?
                    """, (pos.holding_bars, float(mtm_price), bid_p, ask_p, mkt_ts or None, pos.id))
                    conn.commit()
                updated_positions.append(pos)

        return updated_positions, closed_trades

    def reset_account(self, initial_capital: float = 100000.0) -> Dict[str, Union[float, int, str, bool]]:
        """Resets the virtual paper trading account to a fresh starting capital balance and clears positions/trades."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM positions WHERE account_id = ?", (self.account_id,))
            cursor.execute("DELETE FROM trades WHERE account_id = ?", (self.account_id,))
            cursor.execute("DELETE FROM orders WHERE account_id = ?", (self.account_id,))
            cursor.execute("DELETE FROM equity_history WHERE account_id = ?", (self.account_id,))
            cursor.execute(
                """
                UPDATE accounts
                SET initial_capital = ?, current_cash = ?, realized_pnl = 0.0,
                    peak_equity = ?, max_drawdown_pct = 0.0, updated_at = ?
                WHERE id = ?
                """,
                (float(initial_capital), float(initial_capital), float(initial_capital), now_str, self.account_id),
            )
            conn.commit()
        return self.get_account_summary()

    def queue_pre_market_order(
        self,
        ticker: str,
        direction: str,
        current_price: float,
        target_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        allocation_weight_pct: float = 10.0,
        custom_allocated_capital: Optional[float] = None,
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Queues a virtual order for execution at market open, placing a soft hold on required cash."""
        ticker = ticker.upper()
        summary = self.get_account_summary()
        cash = float(summary.get("current_cash", 0.0))
        reserved = float(summary.get("reserved_cash", 0.0))
        available_cash = max(0.0, cash - reserved)
        total_equity = float(summary.get("total_equity", 100000.0))

        if custom_allocated_capital is not None and custom_allocated_capital > 0:
            alloc_cap = min(float(custom_allocated_capital), available_cash)
        else:
            target_alloc = total_equity * (allocation_weight_pct / 100.0)
            alloc_cap = min(target_alloc, available_cash)

        if alloc_cap < 50.0:
            raise ValueError(
                f"Insufficient unreserved cash (${available_cash:.2f}) to queue order for {ticker}"
            )

        shares = alloc_cap / current_price if current_price > 0 else 0.0
        now_str = datetime.now(timezone.utc).isoformat()
        tp = float(target_price) if target_price is not None else 0.0
        sp = float(stop_price) if stop_price is not None else 0.0
        lim_p = float(limit_price) if limit_price is not None else 0.0

        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO orders (
                    account_id, ticker, direction, order_type, shares, price, limit_price,
                    filled_shares, remaining_shares, allocated_capital,
                    target_price, stop_price, submitted_at, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?, ?, ?, ?, 'PRE_MARKET_PENDING')
            """, (
                self.account_id, ticker, direction.upper(), order_type.upper(), shares, current_price,
                lim_p, shares, alloc_cap, tp, sp, now_str, now_str
            ))
            order_num = cursor.lastrowid
            order_id_str = f"ORD-{order_num}"
            cursor.execute("UPDATE orders SET order_id = ? WHERE id = ?", (order_id_str, order_num))
            conn.commit()

        logger.info(
            f"📋 [PAPER] Queued PRE_MARKET_PENDING order #{order_id_str} on {ticker} ({direction}) | Alloc: ${alloc_cap:,.2f}"
        )
        return {
            "id": order_num,
            "order_id": order_id_str,
            "account_id": self.account_id,
            "ticker": ticker,
            "direction": direction.upper(),
            "order_type": order_type.upper(),
            "shares": round(shares, 4),
            "price": current_price,
            "limit_price": lim_p,
            "allocated_capital": round(alloc_cap, 2),
            "target_price": tp,
            "stop_price": sp,
            "status": "PRE_MARKET_PENDING",
            "submitted_at": now_str,
            "created_at": now_str,
        }

    def get_pending_orders(self, ticker: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves all active pending/working/partially-filled orders for this account."""
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            if ticker:
                cursor.execute("""
                    SELECT * FROM orders
                    WHERE account_id = ? AND ticker = ? AND status IN ('PRE_MARKET_PENDING', 'WORKING', 'PARTIALLY_FILLED')
                    ORDER BY id ASC
                """, (self.account_id, ticker.upper()))
            else:
                cursor.execute("""
                    SELECT * FROM orders
                    WHERE account_id = ? AND status IN ('PRE_MARKET_PENDING', 'WORKING', 'PARTIALLY_FILLED')
                    ORDER BY id ASC
                """, (self.account_id,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_order_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves complete persistent order state history (FILLED, PARTIALLY_FILLED, WORKING, REJECTED, CANCELLED)."""
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM orders WHERE account_id = ? ORDER BY id DESC LIMIT ?
            """, (self.account_id, limit))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def cancel_pending_order(self, order_id: Union[int, str]) -> bool:
        """Cancels a pending or working order and releases soft cash hold."""
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE orders
                SET status = 'CANCELLED', cancellation_reason = 'USER_CANCEL'
                WHERE (id = ? OR order_id = ?) AND account_id = ?
                  AND status IN ('PRE_MARKET_PENDING', 'WORKING', 'PARTIALLY_FILLED')
            """, (str(order_id), str(order_id), self.account_id))
            conn.commit()
            success = cursor.rowcount > 0

        if success:
            logger.info(f"🚫 [PAPER] Cancelled order {order_id} for {self.account_id}")
        return success

    def execute_pending_orders_for_ticker(
        self,
        ticker: str,
        opening_price: float,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
    ) -> List[Position]:
        """Executes all PRE_MARKET_PENDING orders for `ticker` upon market open."""
        if opening_price is None or math.isnan(float(opening_price)) or float(opening_price) <= 0:
            return []

        executed_positions = []
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM orders
                WHERE account_id = ? AND ticker = ? AND status = 'PRE_MARKET_PENDING'
                ORDER BY id ASC
            """, (self.account_id, ticker.upper()))
            orders = cursor.fetchall()

        for ord_row in orders:
            ord_id = ord_row["id"]
            direction = ord_row["direction"]
            alloc_cap = float(ord_row["allocated_capital"])
            target_p = float(ord_row["target_price"])
            stop_p = float(ord_row["stop_price"])

            pos = self.open_position(
                ticker=ticker,
                direction=direction,
                current_price=opening_price,
                target_price=target_p,
                stop_price=stop_p,
                allocation_weight_pct=0.0,
                custom_allocated_capital=alloc_cap,
                bid_price=bid_price,
                ask_price=ask_price,
            )
            if pos:
                now_str = datetime.now(timezone.utc).isoformat()
                with self.ledger._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE orders
                        SET status = 'FILLED', fill_price = ?, filled_shares = ?, remaining_shares = 0.0,
                            fee_paid = ?, filled_at = ?, executed_at = ?
                        WHERE id = ?
                    """, (pos.entry_price, pos.shares, pos.entry_fee, now_str, now_str, ord_id))
                    conn.commit()
                executed_positions.append(pos)
                logger.info(
                    f"🚀 [PAPER] Executed pending order #{ord_id} on {ticker} @ {pos.entry_price:.4f} -> Position #{pos.id}"
                )
        return executed_positions

    def close_all_positions(self, current_prices: Dict[str, float], reason: str = "FLATTEN_ALL") -> List[TradeLog]:
        """Liquidates all currently open virtual positions at the provided market prices."""
        open_positions = self.get_open_positions()
        closed = []
        for pos in open_positions:
            exit_p = current_prices.get(pos.ticker, pos.current_price or pos.entry_price)
            tr = self.close_position(pos.id, exit_p, exit_reason=reason)
            if tr is not None:
                closed.append(tr)
        return closed

    def get_closed_trades(self, limit: int = 100) -> List[TradeLog]:
        """Retrieves history of verified completed virtual trades."""
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trades WHERE account_id = ? ORDER BY id DESC LIMIT ?
            """, (self.account_id, limit))
            rows = cursor.fetchall()

        trades = []
        for r in rows:
            keys = r.keys()
            trades.append(
                TradeLog(
                    id=r["id"],
                    ticker=r["ticker"],
                    direction=r["direction"],
                    entry_price=r["entry_price"],
                    exit_price=r["exit_price"],
                    shares=r["shares"],
                    gross_pnl=r["gross_pnl"],
                    friction_fee=r["friction_fee"],
                    net_pnl=r["net_pnl"],
                    return_pct=r["return_pct"],
                    entry_time=r["entry_time"],
                    exit_time=r["exit_time"],
                    exit_reason=r["exit_reason"],
                    slippage_cost=float(r["slippage_cost"]) if ("slippage_cost" in keys and r["slippage_cost"]) else 0.0,
                    commission_fee=float(r["commission_fee"]) if ("commission_fee" in keys and r["commission_fee"]) else float(r["friction_fee"]),
                    market_timestamp=str(r["market_timestamp"]) if ("market_timestamp" in keys and r["market_timestamp"]) else "",
                    session_id=str(r["session_id"]) if ("session_id" in keys and r["session_id"]) else None,
                )
            )
        return trades

    def get_performance_audit(self) -> Dict[str, Union[float, int]]:
        """Computes statistical audit: Win Rate, Profit Factor, Sharpe Ratio, Max Drawdown, Transaction Costs."""
        trades = self.get_closed_trades(limit=1000)
        summary = self.get_account_summary()
        max_dd = float(summary.get("max_drawdown_pct", 0.0))
        total_costs = float(summary.get("total_transaction_costs", 0.0))

        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown_pct": round(max_dd, 2),
                "total_transaction_costs": round(total_costs, 2),
                "net_profit": 0.0,
                "avg_trade_return_pct": 0.0,
            }

        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        gross_win = sum(t.net_pnl for t in wins)
        gross_loss = abs(sum(t.net_pnl for t in losses))

        profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (2.0 if gross_win > 0 else 1.0)
        win_rate = (len(wins) / len(trades)) * 100.0

        returns = np.array([float(t.return_pct) for t in trades], dtype=float)
        if len(returns) >= 2 and float(np.std(returns)) > 1e-6:
            sharpe = float((np.mean(returns) / np.std(returns)) * np.sqrt(min(252, max(10, len(returns)))))
        elif len(returns) == 1 and returns[0] != 0:
            sharpe = 1.5 if returns[0] > 0 else -1.5
        else:
            sharpe = 0.0

        # Also check historical equity curve drawdown across closed trades in chronological order
        chron_trades = list(reversed(trades))
        initial_cap = float(summary.get("initial_capital", 100000.0))
        running_eq = initial_cap
        peak_eq = initial_cap
        curve_max_dd = max_dd
        for t in chron_trades:
            running_eq += float(t.net_pnl)
            peak_eq = max(peak_eq, running_eq)
            dd = ((peak_eq - running_eq) / peak_eq * 100.0) if peak_eq > 0 else 0.0
            curve_max_dd = max(curve_max_dd, dd)

        return {
            "total_trades": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown_pct": round(curve_max_dd, 2),
            "total_transaction_costs": round(total_costs, 2),
            "net_profit": round(sum(t.net_pnl for t in trades), 2),
            "avg_trade_return_pct": round(sum(t.return_pct for t in trades) / len(trades), 2),
        }
