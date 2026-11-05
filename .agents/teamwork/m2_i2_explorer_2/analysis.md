# Technical Analysis: Cross-Session Telemetry Leakage & Zero-Trade Isolation Blueprint

**Target Component**: `src/execution/session_manager.py` (lines 730–760) & `src/execution/broker.py`  
**Test Reference**: `tests/test_m2_challenger_lifecycle.py`  
**Author**: Milestone 2 Iteration 2 Explorer 2 (`m2_i2_explorer_2`)  
**Date**: 2026-11-05  

---

## 1. Executive Summary

During Milestone 2 Iteration 1 verification, an empirical stress test authored by `m2_challenger_1` failed:
```
tests/test_m2_challenger_lifecycle.py::TestEmpiricalEdgeCases::test_stress_session_isolation_and_no_telemetry_leakage FAILED
AssertionError: VULNERABILITY: Session sess_2c4db634f817 leaked 1 trades from prior session sess_ea8cde700967!
assert 1 == 0
```

Investigation reveals a critical ledger boundary defect in `SessionManager.compute_session_performance()`:
When calculating metrics for a session with 0 closed trades, lines 746–748 execute a fallback query:
```python
if not closed_trades:
    cursor.execute("SELECT * FROM trades WHERE account_id = ?", (session.account_id,))
    closed_trades = cursor.fetchall()
```
Lines 752–754 repeat the exact same fallback for `open_positions`:
```python
if not open_positions:
    cursor.execute("SELECT * FROM positions WHERE status = 'OPEN' AND account_id = ?", (session.account_id,))
    open_positions = cursor.fetchall()
```

Because all sessions on a given account (e.g. `PAPER_DEFAULT`) share the same `account_id`, this fallback mistakenly attributes historical trades, win rates, realized P&L, invested equity, and open positions from earlier sessions to any new session.

This document provides the exhaustive root-cause analysis, empirical reproduction, mathematical validation of clean zero-trade accounting, and the production-grade fix blueprint.

---

## 2. Root Cause Analysis

### 2.1 The Flawed Fallback Mechanism
In `src/execution/session_manager.py`:
```python
743:             # Attempt filter by session_id first, fallback to account_id
744:             cursor.execute("SELECT * FROM trades WHERE session_id = ?", (session_id,))
745:             closed_trades = cursor.fetchall()
746:             if not closed_trades:
747:                 cursor.execute("SELECT * FROM trades WHERE account_id = ?", (session.account_id,))
748:                 closed_trades = cursor.fetchall()
749: 
750:             cursor.execute("SELECT * FROM positions WHERE status = 'OPEN' AND session_id = ?", (session_id,))
751:             open_positions = cursor.fetchall()
752:             if not open_positions:
753:                 cursor.execute("SELECT * FROM positions WHERE status = 'OPEN' AND account_id = ?", (session.account_id,))
754:                 open_positions = cursor.fetchall()
```

#### Why Was This Implemented?
The fallback was originally added as a heuristic to support legacy unassigned ledger entries that lacked a `session_id`.

#### Why Is It Catastrophic?
1. **Conflating "Empty Set" with "Query Failure"**: A newly started session having 0 closed trades is not an error; it is the standard, expected initial condition. Evaluating `if not closed_trades:` on an empty list evaluates to `True`, triggering an account-wide search that fetches all historical trades ever executed by that account.
2. **Cross-Session Ledger Breach**: If Session 1 executed 5 trades on `TEST_ACC` with +$1,500 P&L and finished, and Session 2 is created on `TEST_ACC`, Session 2's dashboard telemetry immediately displays:
   - `total_trades`: 5
   - `winning_trades`: inherited from Session 1
   - `realized_pnl`: +$1,500
   - `win_rate_pct`: inherited from Session 1
   - `current_cash`: starting capital + Session 1's P&L!
3. **Open Position Contamination**: When a session ends with `session_end_policy = 'KEEP_OPEN'`, its open positions remain in the database with status `OPEN`. When a subsequent session launches, `if not open_positions:` triggers and attaches the prior session's open positions to the new session, distorting `invested_equity`, `unrealized_pnl`, and `open_positions_count`.

---

## 3. Deep Investigation: The Silent Dependency in `test_stress_compute_performance_accounting_accuracy`

During our deep-dive into `tests/test_m2_challenger_lifecycle.py`, we uncovered a subtle interplay between `PaperBroker` and `SessionManager`:

### 3.1 Observation of Test Implementations
In `test_stress_session_isolation_and_no_telemetry_leakage` (lines 823–852):
```python
# Session 1:
s1 = _create_sample_session(mgr, acc_id, capital=20000.0)
mgr.start_session(s1.id)
broker.active_session_id = s1.id  # <-- Explicitly set!
pos = broker.open_position("AAPL", "LONG", ...)
broker.close_position(...)
mgr.stop_session(s1.id)

# Session 2:
s2 = _create_sample_session(mgr, acc_id, capital=25000.0)
mgr.start_session(s2.id)
perf_s2 = mgr.compute_session_performance(s2.id)
assert perf_s2["total_trades"] == 0
```
Notice that line 832 explicitly set `broker.active_session_id = s1.id`.

However, in `test_stress_compute_performance_accounting_accuracy` (lines 791–822):
```python
session = _create_sample_session(mgr, acc_id, capital=50000.0)
mgr.start_session(session.id)  # Note: bot is NOT passed here!

# Trade 1:
pos1 = broker.open_position("AAPL", "LONG", ...)
broker.close_position(pos1.id, exit_price=105.0, exit_reason="TARGET")
```
Notice:
1. `mgr.start_session(session.id)` was called without passing `bot`.
2. `broker.active_session_id` was NOT manually set.
3. In `PaperBroker.open_position()`:
   ```python
   effective_session_id = session_id or getattr(self, "active_session_id", None)
   ```
   Because `session_id` was not passed and `broker.active_session_id` was `None`, `pos1` and `pos2` were stored in SQLite with `session_id = NULL`!
4. When `close_position()` was called, the trade record was also stored with `session_id = NULL`!
5. In the original code, `test_stress_compute_performance_accounting_accuracy` only passed because `compute_session_performance()` fell back to `SELECT * FROM trades WHERE account_id = ?`!

### 3.2 Architectural Implication
If an implementer *only* deletes the fallback in `compute_session_performance()` without addressing broker session attribution:
- `test_stress_session_isolation_and_no_telemetry_leakage` will PASS.
- BUT `test_stress_compute_performance_accounting_accuracy` will FAIL (`assert 0 == 2`) because the broker never tagged its trades with `session_id`!

Therefore, a robust fix blueprint must solve both sides:
1. **Strict Session Isolation**: Eliminate the fallback in `compute_session_performance()`.
2. **Broker Session Auto-Resolution**: Ensure `PaperBroker.open_position()` automatically resolves `effective_session_id` from the database if `self.active_session_id` has not been manually injected, guaranteeing that any order/position opened while a session is `RUNNING` is tagged correctly.

---

## 4. Mathematical Clean Zero-Trade Accounting Verification

When a session has 0 closed trades, the performance calculation must yield clean, zeroed accounting while accurately reflecting capital and cash holds:

| Field | Expression / Logic | Zero-Trade State | 1 Open Position State |
|---|---|---|---|
| `total_trades` | `len(closed_trades)` | `0` | `0` |
| `winning_trades` | `sum(1 for t in closed_trades if net_pnl > 0)` | `0` | `0` |
| `losing_trades` | `sum(1 for t in closed_trades if net_pnl < 0)` | `0` | `0` |
| `win_rate_pct` | `(winning / total) * 100 if total > 0 else 0.0` | `0.0` | `0.0` |
| `realized_pnl` | `sum(net_pnl for t in closed_trades) if closed_trades else 0.0` | `0.0` | `0.0` |
| `gross_profit` | `sum(net_pnl for t in closed_trades if net_pnl > 0)` | `0.0` | `0.0` |
| `gross_loss` | `abs(sum(net_pnl for t in closed_trades if net_pnl < 0))` | `0.0` | `0.0` |
| `profit_factor` | `round(gp / gl, 2) if gl > 0 else (999.99 if gp > 0 else 1.0)` | `1.0` | `1.0` |
| `invested_equity` | `sum(allocated_capital for p in open_positions)` | `0.0` | `pos.allocated_capital` |
| `unrealized_pnl` | `sum(MTM pnl for p in open_positions)` | `0.0` | `(last_p - entry_p) * shares` |
| `starting_capital` | `float(session.allocated_capital)` | `initial_cap` | `initial_cap` |
| `current_cash` | `max(0.0, initial_cap + realized_pnl - invested_equity)` | `initial_cap` | `initial_cap - invested_equity` |
| `total_equity` | `current_cash + invested_equity + unrealized_pnl` | `initial_cap` | `initial_cap + unrealized_pnl` |
| `net_pnl` | `realized_pnl + unrealized_pnl` | `0.0` | `unrealized_pnl` |
| `return_pct` | `round((net_pnl / initial_cap) * 100, 2)` | `0.0` | `round((unrealized / initial_cap) * 100, 2)` |
| `open_positions_count` | `len(open_positions)` | `0` | `len(open_positions)` |

All values strictly partition by `session_id`, leaving zero leakage across session boundaries.

---

## 5. Recommended Fix Blueprint

### 5.1 Step 1: Strict Session-Scoped Query in `src/execution/session_manager.py`

**File**: `src/execution/session_manager.py`  
**Target Lines**: 740–755  

#### Current Code (Vulnerable):
```python
        # Query closed trades for this session or account
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            # Attempt filter by session_id first, fallback to account_id
            cursor.execute("SELECT * FROM trades WHERE session_id = ?", (session_id,))
            closed_trades = cursor.fetchall()
            if not closed_trades:
                cursor.execute("SELECT * FROM trades WHERE account_id = ?", (session.account_id,))
                closed_trades = cursor.fetchall()

            cursor.execute("SELECT * FROM positions WHERE status = 'OPEN' AND session_id = ?", (session_id,))
            open_positions = cursor.fetchall()
            if not open_positions:
                cursor.execute("SELECT * FROM positions WHERE status = 'OPEN' AND account_id = ?", (session.account_id,))
                open_positions = cursor.fetchall()
```

#### Proposed Replacement (Strict Isolation):
```python
        # Query closed trades and open positions strictly partitioned by session_id
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM trades WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            )
            closed_trades = cursor.fetchall()

            cursor.execute(
                "SELECT * FROM positions WHERE status = 'OPEN' AND session_id = ? ORDER BY id ASC",
                (session_id,),
            )
            open_positions = cursor.fetchall()
```

---

### 5.2 Step 2: Auto-Resolve Running Session in `src/execution/broker.py`

To ensure that direct calls to `PaperBroker.open_position()` or tests that call `mgr.start_session(session.id)` without passing `bot` do not produce orphan positions with `session_id = NULL`, add auto-resolution:

**File**: `src/execution/broker.py`  
**Target Line**: 846 (`open_position()`)  

#### Proposed Replacement:
```python
        now_str = datetime.now(timezone.utc).isoformat()
        mkt_ts = str(market_timestamp or now_str)
        effective_session_id = session_id or getattr(self, "active_session_id", None)
        if not effective_session_id:
            try:
                with self.ledger._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id FROM trading_sessions WHERE account_id = ? AND status = 'RUNNING' ORDER BY started_at DESC, created_at DESC LIMIT 1",
                        (self.account_id,),
                    )
                    row = cursor.fetchone()
                    if row:
                        effective_session_id = str(row["id"])
                        self.active_session_id = effective_session_id
            except Exception:
                pass
```

And in `_record_order_event()` / `queue_pre_market_order()`, also ensure `session_id` is recorded into `orders`:
```python
        effective_session_id = session_id or getattr(self, "active_session_id", None)
```

---

### 5.3 Step 3: Hardening `tests/test_m2_challenger_lifecycle.py`

In `tests/test_m2_challenger_lifecycle.py`, line 798 of `test_stress_compute_performance_accounting_accuracy`:
Explicitly associate the broker with the started session (matching line 832):
```python
        session = _create_sample_session(mgr, acc_id, capital=50000.0)
        mgr.start_session(session.id)
        broker.active_session_id = session.id
```
This guarantees explicit attribution in the test suite alongside the runtime defensive auto-resolution.

---

## 6. Empirical Validation Script

We developed and executed an automated verification script:  
`C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_explorer_2\verify_fix.py`

The test harness evaluated four comprehensive stress cases:
1. **Strict Session Isolation**: Session 1 completes +$50 trade and stops. Session 2 starts with 0 trades. Verified: `total_trades = 0`, `realized_pnl = 0.0`, `win_rate_pct = 0.0`, `current_cash = 25000.0`, `total_equity = 25000.0`.
2. **Keep-Open Position Isolation**: Session 1 stops under `KEEP_OPEN` leaving an open AAPL position. Session 2 starts. Verified: Session 2 queries 0 open positions.
3. **Mixed Accounting Accuracy**: Session with 1 win (AAPL), 1 loss (MSFT), and 1 open position (GOOGL). Verified: `total_trades = 2`, `win_rate_pct = 50.0%`, `open_positions_count = 1`, and cash exactly equals `initial_cap + realized_pnl - invested_equity`.
4. **Broker Auto-Resolution**: When `broker.active_session_id` is `None`, broker automatically resolves the active `RUNNING` session ID from SQLite.

### Test Execution Output:
```
[1] Isolation test PASSED: 0 trades, 0.0 PnL, cash exactly matches starting capital.
[2] Position isolation test PASSED: Kept-open position from Session 1 did NOT leak to Session 2!
[3] Mixed accounting test PASSED: total_trades=2, win_rate=50.0%, realized_pnl=282.58, cash=45282.58
[4] Auto-resolution test PASSED: Broker dynamically resolved active RUNNING session ID.

ALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!
```

---

## 7. Downstream Impact Assessment for Milestone 3

Eliminating cross-session telemetry leakage directly benefits the Milestone 3 Frontend UI:
- **`SessionTelemetryBar.tsx`**: When a user launches a new session from the Trading Session Setup Wizard, initial financial indicators will cleanly render:
  - Total Trades: `0`
  - Win Rate: `0.0%`
  - Realized P&L: `₹0.00` or `$0.00`
  - Available Cash: exactly `allocated_capital`
  - Open Positions: `0`
- Zero false historical data will appear on newly minted sessions.
