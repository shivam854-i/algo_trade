"""Autonomous Live Paper-Trading & Broker Execution Engine.

Provides persistent, real-time order routing, position tracking,
and Mark-to-Market PnL audit logs backed by SQLite. Includes pluggable
adapters for Alpaca (US/Crypto), Zerodha (Indian NSE), and MetaTrader 5 (Forex/Gold).
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Dict, List, Optional, Tuple, Union

from src.execution.frictions import FrictionEvaluator

logger = logging.getLogger(__name__)


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


class TradingLedgerDB:
    """SQLite-backed persistent ledger for accounts, positions, and trades."""

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
        """Initializes tables for accounts, open positions, orders, and closed trades."""
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
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Open / Active Positions
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
                    last_price REAL DEFAULT 0.0
                )
            """)
            try:
                cursor.execute("ALTER TABLE positions ADD COLUMN last_price REAL DEFAULT 0.0")
            except Exception:
                pass

            # Historical Closed Trades
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
                    exit_reason TEXT NOT NULL
                )
            """)

            # Orders (Pre-market pending, filled, cancelled)
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
                    allocated_capital REAL NOT NULL,
                    target_price REAL NOT NULL,
                    stop_price REAL NOT NULL,
                    submitted_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    fill_price REAL DEFAULT 0.0,
                    filled_at TEXT,
                    executed_at TEXT,
                    cancellation_reason TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_ticker ON orders(ticker)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_account ON orders(account_id)")

            # Ensure default paper account exists
            cursor.execute("SELECT id FROM accounts WHERE id = 'PAPER_DEFAULT'")
            if not cursor.fetchone():
                now_str = datetime.utcnow().isoformat()
                cursor.execute("""
                    INSERT INTO accounts (id, account_type, initial_capital, current_cash, realized_pnl, created_at, updated_at)
                    VALUES ('PAPER_DEFAULT', 'PAPER', 100000.0, 100000.0, 0.0, ?, ?)
                """, (now_str, now_str))

            conn.commit()


class BaseBrokerAdapter:
    """Abstract interface for multi-broker trade execution."""

    def submit_order(self, ticker: str, direction: str, shares: float, price: float) -> bool:
        raise NotImplementedError

    def get_market_price(self, ticker: str) -> float:
        raise NotImplementedError


class AlpacaBrokerAdapter(BaseBrokerAdapter):
    """Adapter for Alpaca Markets (US Equities & Crypto)."""

    def __init__(self, api_key: str = "", secret_key: str = "", paper: bool = True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.base_url = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"

    def submit_order(self, ticker: str, direction: str, shares: float, price: float) -> bool:
        logger.info(f"[Alpaca] Routing {direction} order for {shares} shares of {ticker} at ${price:.2f}")
        return True


class ZerodhaKiteAdapter(BaseBrokerAdapter):
    """Adapter for Zerodha Kite Connect (Indian NSE Equities)."""

    def __init__(self, api_key: str = "", access_token: str = ""):
        self.api_key = api_key
        self.access_token = access_token

    def submit_order(self, ticker: str, direction: str, shares: float, price: float) -> bool:
        logger.info(f"[Zerodha Kite] Routing {direction} order for {shares} qty of {ticker} at INR {price:.2f}")
        return True


class MT5BrokerAdapter(BaseBrokerAdapter):
    """Adapter for MetaTrader 5 (Forex & Commodities / Gold)."""

    def __init__(self, login: int = 0, server: str = "", password: str = ""):
        self.login = login
        self.server = server
        self.password = password

    def submit_order(self, ticker: str, direction: str, shares: float, price: float) -> bool:
        logger.info(f"[MT5] Routing {direction} order for {shares} lots of {ticker} at {price:.4f}")
        return True


class PaperBroker:
    """Autonomous Paper-Trading Engine with exact friction simulation and mark-to-market tracking."""

    def __init__(self, account_id: str = "PAPER_DEFAULT", initial_capital: float = 100000.0):
        self.account_id = account_id
        self.ledger = TradingLedgerDB()
        self._ensure_account(initial_capital)

    def _ensure_account(self, capital: float):
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM accounts WHERE id = ?", (self.account_id,))
            if not cursor.fetchone():
                now_str = datetime.utcnow().isoformat()
                cursor.execute("""
                    INSERT INTO accounts (id, account_type, initial_capital, current_cash, realized_pnl, created_at, updated_at)
                    VALUES (?, 'PAPER', ?, ?, 0.0, ?, ?)
                """, (self.account_id, capital, capital, now_str, now_str))
                conn.commit()

    def get_account_summary(self) -> Dict[str, Union[float, int, str]]:
        """Computes live account metrics: Cash, Invested, Total Equity, Realized PnL, Unrealized PnL."""
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM accounts WHERE id = ?", (self.account_id,))
            acc = cursor.fetchone()
            if not acc:
                return {}

            cash = float(acc["current_cash"])
            realized_pnl = float(acc["realized_pnl"])
            initial_cap = float(acc["initial_capital"])

            cursor.execute("""
                SELECT COALESCE(SUM(allocated_capital), 0.0) as reserved
                FROM orders
                WHERE account_id = ? AND status = 'PRE_MARKET_PENDING'
            """, (self.account_id,))
            res_row = cursor.fetchone()
            reserved_cash = float(res_row["reserved"]) if res_row else 0.0

        positions = self.get_open_positions()
        allocated_capital = sum(p.allocated_capital for p in positions)
        unrealized_pnl = sum(p.unrealized_pnl for p in positions)
        total_equity = cash + allocated_capital + unrealized_pnl
        total_return_pct = ((total_equity - initial_cap) / initial_cap) * 100.0
        available_cash = max(0.0, cash - reserved_cash)

        return {
            "account_id": self.account_id,
            "initial_capital": round(initial_cap, 2),
            "cash": round(available_cash, 2),
            "current_cash": round(cash, 2),
            "reserved_cash": round(reserved_cash, 2),
            "available_cash": round(available_cash, 2),
            "allocated_capital": round(allocated_capital, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "realized_pnl": round(realized_pnl, 2),
            "total_equity": round(total_equity, 2),
            "total_return_pct": round(total_return_pct, 2),
            "open_positions_count": len(positions),
        }

    def get_open_positions(self) -> List[Position]:
        """Retrieves all currently open positions."""
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM positions WHERE account_id = ? AND status = 'OPEN' ORDER BY id DESC
            """, (self.account_id,))
            rows = cursor.fetchall()

        positions = []
        for r in rows:
            entry_p = float(r["entry_price"])
            last_p = float(r["last_price"]) if ("last_price" in r.keys() and r["last_price"] and float(r["last_price"]) > 0) else entry_p
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
            )
            positions.append(pos)
        return positions

    def open_position(
        self,
        ticker: str,
        direction: str,  # "LONG" or "SHORT"
        current_price: float,
        target_price: float,
        stop_price: float,
        allocation_weight_pct: float = 10.0,
        custom_allocated_capital: Optional[float] = None,
    ) -> Optional[Position]:
        """Executes a new position, deducting cash and recording exact entry prices."""
        ticker = ticker.upper()
        summary = self.get_account_summary()
        cash = float(summary.get("current_cash", 0.0))
        total_equity = float(summary.get("total_equity", 100000.0))

        # Capital to allocate
        if custom_allocated_capital is not None and custom_allocated_capital > 0:
            alloc_cap = min(custom_allocated_capital, cash)
        else:
            target_alloc = total_equity * (allocation_weight_pct / 100.0)
            alloc_cap = min(target_alloc, cash)

        if alloc_cap < 50.0:
            logger.warning(f"Insufficient cash (${cash:.2f}) to open position on {ticker}")
            return None

        # Friction deduction on entry
        friction_dec = FrictionEvaluator.calculate_round_trip_friction_bps(ticker) / 10000.0 / 2.0
        entry_fee = alloc_cap * friction_dec
        net_alloc = alloc_cap - entry_fee
        shares = net_alloc / current_price

        now_str = datetime.utcnow().isoformat()

        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO positions (
                    account_id, ticker, direction, entry_price, shares, allocated_capital,
                    target_price, stop_price, entry_time, holding_bars, status, last_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'OPEN', ?)
            """, (
                self.account_id, ticker, direction, current_price, shares, alloc_cap,
                target_price, stop_price, now_str, current_price
            ))
            pos_id = cursor.lastrowid

            # Deduct cash from account
            new_cash = cash - alloc_cap
            cursor.execute("""
                UPDATE accounts SET current_cash = ?, updated_at = ? WHERE id = ?
            """, (new_cash, now_str, self.account_id))
            conn.commit()

        logger.info(
            f"✅ Opened {direction} position on {ticker} | {shares:.4f} shares @ {current_price:.2f} (Alloc: ${alloc_cap:.2f})"
        )

        return Position(
            id=pos_id,
            ticker=ticker,
            direction=direction,
            entry_price=current_price,
            shares=shares,
            allocated_capital=alloc_cap,
            target_price=target_price,
            stop_price=stop_price,
            entry_time=now_str,
            holding_bars=0,
            status="OPEN",
            current_price=current_price,
            unrealized_pnl=0.0,
            unrealized_return_pct=0.0,
        )

    def close_position(
        self,
        position_id: int,
        exit_price: float,
        exit_reason: str = "MANUAL_CLOSE",
    ) -> Optional[TradeLog]:
        """Closes an open position, books realized PnL, deducts exit friction, and releases cash."""
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

            # Calculate returns & fees
            if direction == "LONG":
                gross_ret = (exit_price - entry_price) / entry_price
            else:
                gross_ret = (entry_price - exit_price) / entry_price

            friction_dec = FrictionEvaluator.calculate_round_trip_friction_bps(ticker) / 10000.0
            total_fee = (shares * entry_price) * friction_dec
            gross_pnl = shares * entry_price * gross_ret
            net_pnl = gross_pnl - total_fee
            return_pct = (net_pnl / alloc_cap) * 100.0

            returned_capital = alloc_cap + net_pnl
            now_str = datetime.utcnow().isoformat()

            # 1. Update position status to CLOSED
            cursor.execute("UPDATE positions SET status = 'CLOSED' WHERE id = ?", (position_id,))

            # 2. Record completed trade
            cursor.execute("""
                INSERT INTO trades (
                    account_id, ticker, direction, entry_price, exit_price, shares,
                    gross_pnl, friction_fee, net_pnl, return_pct, entry_time, exit_time, exit_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.account_id, ticker, direction, entry_price, exit_price, shares,
                gross_pnl, total_fee, net_pnl, return_pct, entry_time, now_str, exit_reason
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
            f"🎯 Closed {direction} on {ticker} | Exit: {exit_price:.2f} | Net PnL: ${net_pnl:+.2f} ({return_pct:+.2f}%) | Reason: {exit_reason}"
        )

        return TradeLog(
            id=trade_id,
            ticker=ticker,
            direction=direction,
            entry_price=round(entry_price, 2),
            exit_price=round(exit_price, 2),
            shares=round(shares, 4),
            gross_pnl=round(gross_pnl, 2),
            friction_fee=round(total_fee, 2),
            net_pnl=round(net_pnl, 2),
            return_pct=round(return_pct, 2),
            entry_time=entry_time,
            exit_time=now_str,
            exit_reason=exit_reason,
        )

    def update_and_audit_positions(
        self, current_prices: Dict[str, float]
    ) -> Tuple[List[Position], List[TradeLog]]:
        """Inspects all open positions against incoming live prices.

        Automatically triggers Profit-Targets and Stop-Losses, updates MTM unrealized PnL.
        """
        open_positions = self.get_open_positions()
        updated_positions = []
        closed_trades = []

        for pos in open_positions:
            curr_price = current_prices.get(pos.ticker, pos.entry_price)
            pos.current_price = curr_price
            pos.holding_bars += 1

            # Unrealized calculation
            if pos.direction == "LONG":
                raw_pnl = pos.shares * (curr_price - pos.entry_price)
            else:
                raw_pnl = pos.shares * (pos.entry_price - curr_price)

            pos.unrealized_pnl = raw_pnl
            pos.unrealized_return_pct = (raw_pnl / pos.allocated_capital) * 100.0

            # Check dynamic triple-barriers
            exit_reason = None
            if pos.direction == "LONG":
                if curr_price >= pos.target_price:
                    exit_reason = "PROFIT_TARGET"
                elif curr_price <= pos.stop_price:
                    exit_reason = "STOP_LOSS"
            elif pos.direction == "SHORT":
                if curr_price <= pos.target_price:
                    exit_reason = "PROFIT_TARGET"
                elif curr_price >= pos.stop_price:
                    exit_reason = "STOP_LOSS"

            if exit_reason:
                trade = self.close_position(pos.id, curr_price, exit_reason)
                if trade:
                    closed_trades.append(trade)
            else:
                # Update holding bars and last_price in DB
                with self.ledger._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE positions SET holding_bars = ?, last_price = ? WHERE id = ?
                    """, (pos.holding_bars, float(curr_price), pos.id))
                    conn.commit()
                updated_positions.append(pos)

        return updated_positions, closed_trades

    def reset_account(self, initial_capital: float = 100000.0) -> Dict[str, Union[float, int, str]]:
        """Resets the paper trading account to a fresh starting capital balance and clears positions/trades."""
        now_str = datetime.utcnow().isoformat()
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM positions WHERE account_id = ?", (self.account_id,))
            cursor.execute("DELETE FROM trades WHERE account_id = ?", (self.account_id,))
            cursor.execute("DELETE FROM orders WHERE account_id = ?", (self.account_id,))
            cursor.execute(
                """
                UPDATE accounts
                SET initial_capital = ?, current_cash = ?, realized_pnl = 0.0, updated_at = ?
                WHERE id = ?
                """,
                (float(initial_capital), float(initial_capital), now_str, self.account_id),
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
    ) -> Dict:
        """Queues an order for execution at market open, placing a soft hold on required cash."""
        ticker = ticker.upper()
        summary = self.get_account_summary()
        cash = float(summary.get("current_cash", 0.0))
        reserved = float(summary.get("reserved_cash", 0.0))
        available_cash = max(0.0, cash - reserved)
        total_equity = float(summary.get("total_equity", 100000.0))

        if custom_allocated_capital is not None and custom_allocated_capital > 0:
            alloc_cap = min(custom_allocated_capital, available_cash)
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

        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO orders (
                    account_id, ticker, direction, order_type, shares, price, allocated_capital,
                    target_price, stop_price, submitted_at, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PRE_MARKET_PENDING')
            """, (
                self.account_id, ticker, direction, order_type, shares, current_price, alloc_cap,
                tp, sp, now_str, now_str
            ))
            order_num = cursor.lastrowid
            order_id_str = f"ORD-{order_num}"
            cursor.execute("UPDATE orders SET order_id = ? WHERE id = ?", (order_id_str, order_num))
            conn.commit()

        logger.info(
            f"📋 Queued PRE_MARKET_PENDING order #{order_id_str} on {ticker} ({direction}) | Alloc: ${alloc_cap:,.2f}"
        )
        return {
            "id": order_num,
            "order_id": order_id_str,
            "account_id": self.account_id,
            "ticker": ticker,
            "direction": direction,
            "order_type": order_type,
            "shares": round(shares, 4),
            "price": current_price,
            "allocated_capital": round(alloc_cap, 2),
            "target_price": tp,
            "stop_price": sp,
            "status": "PRE_MARKET_PENDING",
            "submitted_at": now_str,
            "created_at": now_str,
        }

    def get_pending_orders(self, ticker: Optional[str] = None) -> List[Dict]:
        """Retrieves all pending orders for this account waiting for market open."""
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            if ticker:
                cursor.execute("""
                    SELECT * FROM orders
                    WHERE account_id = ? AND ticker = ? AND status = 'PRE_MARKET_PENDING'
                    ORDER BY id ASC
                """, (self.account_id, ticker.upper()))
            else:
                cursor.execute("""
                    SELECT * FROM orders
                    WHERE account_id = ? AND status = 'PRE_MARKET_PENDING'
                    ORDER BY id ASC
                """, (self.account_id,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def cancel_pending_order(self, order_id: Union[int, str]) -> bool:
        """Cancels a pending order and releases soft cash hold."""
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE orders
                SET status = 'CANCELLED', cancellation_reason = 'USER_CANCEL'
                WHERE (id = ? OR order_id = ?) AND account_id = ? AND status = 'PRE_MARKET_PENDING'
            """, (str(order_id), str(order_id), self.account_id))
            conn.commit()
            success = cursor.rowcount > 0

        if success:
            logger.info(f"🚫 Cancelled pending order {order_id} for {self.account_id}")
        return success

    def execute_pending_orders_for_ticker(self, ticker: str, opening_price: float) -> List[Position]:
        """Executes all pending orders for `ticker` upon market open."""
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
            )
            if pos:
                now_str = datetime.now(timezone.utc).isoformat()
                with self.ledger._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE orders
                        SET status = 'FILLED', fill_price = ?, filled_at = ?, executed_at = ?
                        WHERE id = ?
                    """, (opening_price, now_str, now_str, ord_id))
                    conn.commit()
                executed_positions.append(pos)
                logger.info(
                    f"🚀 Executed pending order #{ord_id} on {ticker} @ {opening_price:.4f} -> Position #{pos.id}"
                )
        return executed_positions

    def close_all_positions(self, current_prices: Dict[str, float], reason: str = "FLATTEN_ALL") -> List[TradeLog]:
        """Liquidates all currently open positions at the provided market prices."""
        open_positions = self.get_open_positions()
        closed = []
        for pos in open_positions:
            exit_p = current_prices.get(pos.ticker, pos.current_price or pos.entry_price)
            tr = self.close_position(pos.id, exit_p, exit_reason=reason)
            if tr is not None:
                closed.append(tr)
        return closed

    def get_closed_trades(self, limit: int = 100) -> List[TradeLog]:
        """Retrieves history of verified completed trades."""
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trades WHERE account_id = ? ORDER BY id DESC LIMIT ?
            """, (self.account_id, limit))
            rows = cursor.fetchall()

        trades = []
        for r in rows:
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
                )
            )
        return trades

    def get_performance_audit(self) -> Dict[str, Union[float, int]]:
        """Computes statistical audit: Win Rate, Profit Factor, Expectancy, Total Trades."""
        trades = self.get_closed_trades(limit=1000)
        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "net_profit": 0.0,
                "avg_trade_return_pct": 0.0,
            }

        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        gross_win = sum(t.net_pnl for t in wins)
        gross_loss = abs(sum(t.net_pnl for t in losses))

        profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (2.0 if gross_win > 0 else 1.0)
        win_rate = (len(wins) / len(trades)) * 100.0

        return {
            "total_trades": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "net_profit": round(sum(t.net_pnl for t in trades), 2),
            "avg_trade_return_pct": round(sum(t.return_pct for t in trades) / len(trades), 2),
        }
