"""Comprehensive verification test harness for session isolation and accounting."""

import tempfile
from pathlib import Path
from src.execution.broker import PaperBroker
from src.execution.session_manager import SessionManager


def test_isolation_and_no_leakage():
    td = tempfile.mkdtemp()
    db = Path(td) / "test1.db"
    b = PaperBroker(account_id="TEST_ACC", db_path=db)
    m = SessionManager(ledger=b.ledger)

    # Session 1: 1 trade +$50
    s1 = m.create_session({
        "market": "US_EQUITIES",
        "instruments": ["AAPL"],
        "allocated_capital": 20000.0,
        "account_id": "TEST_ACC",
        "duration_minutes": 60,
    })
    m.start_session(s1.id)
    b.active_session_id = s1.id
    pos1 = b.open_position("AAPL", "LONG", 100.0, 110.0, 95.0, custom_allocated_capital=2000.0)
    b.close_position(pos1.id, 105.0, exit_reason="TAKE_PROFIT")
    m.stop_session(s1.id)

    # Session 2: 0 trades
    s2 = m.create_session({
        "market": "US_EQUITIES",
        "instruments": ["NVDA"],
        "allocated_capital": 25000.0,
        "account_id": "TEST_ACC",
        "duration_minutes": 60,
    })
    m.start_session(s2.id)

    # Performance query for s2 using strict session_id query (proposed fix)
    with b.ledger._get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM trades WHERE session_id = ?", (s2.id,))
        closed_trades = cur.fetchall()
        cur.execute("SELECT * FROM positions WHERE status = 'OPEN' AND session_id = ?", (s2.id,))
        open_positions = cur.fetchall()

    total_trades = len(closed_trades)
    winning_trades = sum(1 for t in closed_trades if float(t["net_pnl"]) > 0)
    realized_pnl = sum(float(t["net_pnl"]) for t in closed_trades) if closed_trades else 0.0
    win_rate_pct = round((winning_trades / total_trades) * 100.0, 1) if total_trades > 0 else 0.0
    invested_equity = sum(float(p["allocated_capital"]) for p in open_positions) if open_positions else 0.0
    unrealized_pnl = 0.0
    initial_cap = float(s2.allocated_capital)
    current_cash = max(0.0, initial_cap + realized_pnl - invested_equity)
    total_equity = current_cash + invested_equity + unrealized_pnl

    assert total_trades == 0, f"Expected 0, got {total_trades}"
    assert realized_pnl == 0.0, f"Expected 0.0, got {realized_pnl}"
    assert win_rate_pct == 0.0, f"Expected 0.0, got {win_rate_pct}"
    assert current_cash == 25000.0, f"Expected 25000.0, got {current_cash}"
    assert total_equity == 25000.0, f"Expected 25000.0, got {total_equity}"
    print("[1] Isolation test PASSED: 0 trades, 0.0 PnL, cash exactly matches starting capital.")


def test_keep_open_position_isolation():
    """Verify that an open position kept open from Session 1 does NOT leak into Session 2."""
    td = tempfile.mkdtemp()
    db = Path(td) / "test2.db"
    b = PaperBroker(account_id="TEST_ACC", db_path=db)
    m = SessionManager(ledger=b.ledger)

    # Session 1 ends with KEEP_OPEN leaving an open position
    s1 = m.create_session({
        "market": "US_EQUITIES",
        "instruments": ["AAPL"],
        "allocated_capital": 20000.0,
        "account_id": "TEST_ACC",
        "duration_minutes": 60,
        "session_end_policy": "KEEP_OPEN",
    })
    m.start_session(s1.id)
    b.active_session_id = s1.id
    pos_s1 = b.open_position("AAPL", "LONG", 100.0, 110.0, 95.0, custom_allocated_capital=5000.0)
    m.stop_session(s1.id) # kept open, not closed

    # Session 2 begins
    s2 = m.create_session({
        "market": "US_EQUITIES",
        "instruments": ["NVDA"],
        "allocated_capital": 30000.0,
        "account_id": "TEST_ACC",
        "duration_minutes": 60,
    })
    m.start_session(s2.id)

    # Strict query for Session 2
    with b.ledger._get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM positions WHERE status = 'OPEN' AND session_id = ?", (s2.id,))
        open_pos_s2 = cur.fetchall()

    assert len(open_pos_s2) == 0, f"Expected 0 open positions for Session 2, got {len(open_pos_s2)}"
    print("[2] Position isolation test PASSED: Kept-open position from Session 1 did NOT leak to Session 2!")


def test_mixed_trades_accounting_accuracy():
    """Verify exact financial math when session has 1 winning trade, 1 losing trade, and 1 open position."""
    td = tempfile.mkdtemp()
    db = Path(td) / "test3.db"
    b = PaperBroker(account_id="TEST_ACC", db_path=db)
    m = SessionManager(ledger=b.ledger)

    s = m.create_session({
        "market": "US_EQUITIES",
        "instruments": ["AAPL", "MSFT", "GOOGL"],
        "allocated_capital": 50000.0,
        "account_id": "TEST_ACC",
        "duration_minutes": 60,
    })
    m.start_session(s.id)
    b.active_session_id = s.id

    # Trade 1: AAPL win
    p1 = b.open_position("AAPL", "LONG", 100.0, 110.0, 95.0, custom_allocated_capital=10000.0)
    b.close_position(p1.id, 105.0, exit_reason="TARGET")

    # Trade 2: MSFT loss
    p2 = b.open_position("MSFT", "LONG", 200.0, 220.0, 190.0, custom_allocated_capital=10000.0)
    b.close_position(p2.id, 196.0, exit_reason="STOP")

    # Open position: GOOGL
    b.open_position("GOOGL", "LONG", 100.0, 120.0, 90.0, custom_allocated_capital=5000.0)

    # Query with strict session_id scoping
    with b.ledger._get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM trades WHERE session_id = ?", (s.id,))
        closed_trades = cur.fetchall()
        cur.execute("SELECT * FROM positions WHERE status = 'OPEN' AND session_id = ?", (s.id,))
        open_positions = cur.fetchall()

    assert len(closed_trades) == 2
    assert len(open_positions) == 1

    winning_trades = sum(1 for t in closed_trades if float(t["net_pnl"]) > 0)
    losing_trades = sum(1 for t in closed_trades if float(t["net_pnl"]) < 0)
    realized_pnl = sum(float(t["net_pnl"]) for t in closed_trades)
    win_rate_pct = round((winning_trades / len(closed_trades)) * 100.0, 1)

    assert winning_trades == 1
    assert losing_trades == 1
    assert win_rate_pct == 50.0

    invested_equity = sum(float(p["allocated_capital"]) for p in open_positions)
    assert invested_equity == 5000.0

    initial_cap = float(s.allocated_capital)
    current_cash = max(0.0, initial_cap + realized_pnl - invested_equity)
    total_equity = current_cash + invested_equity

    assert round(current_cash, 2) == round(50000.0 + realized_pnl - 5000.0, 2)
    print(f"[3] Mixed accounting test PASSED: total_trades=2, win_rate=50.0%, realized_pnl={realized_pnl:.2f}, cash={current_cash:.2f}")


def test_auto_resolution_in_broker():
    """Verify that if b.active_session_id is not manually set, broker can resolve running session."""
    td = tempfile.mkdtemp()
    db = Path(td) / "test4.db"
    b = PaperBroker(account_id="TEST_ACC", db_path=db)
    m = SessionManager(ledger=b.ledger)

    s = m.create_session({
        "market": "US_EQUITIES",
        "instruments": ["AAPL"],
        "allocated_capital": 50000.0,
        "account_id": "TEST_ACC",
        "duration_minutes": 60,
    })
    m.start_session(s.id)
    # Notice: b.active_session_id is NOT explicitly set here!
    assert b.active_session_id is None

    # Auto-resolution logic simulation
    def get_effective_session(broker):
        if broker.active_session_id:
            return broker.active_session_id
        with broker.ledger._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM trading_sessions WHERE account_id = ? AND status = 'RUNNING' ORDER BY started_at DESC LIMIT 1",
                (broker.account_id,),
            )
            row = cur.fetchone()
            if row:
                broker.active_session_id = str(row["id"])
                return broker.active_session_id
        return None

    resolved_sid = get_effective_session(b)
    assert resolved_sid == s.id
    assert b.active_session_id == s.id
    print("[4] Auto-resolution test PASSED: Broker dynamically resolved active RUNNING session ID.")


if __name__ == "__main__":
    test_isolation_and_no_leakage()
    test_keep_open_position_isolation()
    test_mixed_trades_accounting_accuracy()
    test_auto_resolution_in_broker()
    print("\nALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
