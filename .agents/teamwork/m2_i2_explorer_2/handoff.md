# Handoff Report — Milestone 2 Iteration 2 Explorer 2

**Author**: Milestone 2 Iteration 2 Explorer 2 (`m2_i2_explorer_2`)  
**Recipient**: Lead Orchestrator (`d0b51128-456f-4a81-855c-2a488d288844`)  
**Mission**: Investigate cross-session telemetry leakage in `compute_session_performance()`, verify test failure in `tests/test_m2_challenger_lifecycle.py`, and design clean zero-trade isolation blueprint.  
**Date**: 2026-11-05  
**Type**: Hard Handoff (Investigation & Blueprint Design Complete)  

---

## 1. Observation

### 1.1 Direct Defect Observation
In `src/execution/session_manager.py` (lines 743–755):
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

### 1.2 Verbatim Test Failure Reproduction
Executed:
```powershell
cmd /c "cd /d C:\Users\Shivam\Desktop\trade_bot && py -m pytest tests/test_m2_challenger_lifecycle.py -k test_stress_session_isolation_and_no_telemetry_leakage -v"
```

Verbatim Output:
```
tests/test_m2_challenger_lifecycle.py::TestEmpiricalEdgeCases::test_stress_session_isolation_and_no_telemetry_leakage FAILED [100%]

================================== FAILURES ===================================
_ TestEmpiricalEdgeCases.test_stress_session_isolation_and_no_telemetry_leakage _
    ...
>       assert perf_s2["total_trades"] == 0, (
            f"VULNERABILITY: Session {s2.id} leaked {perf_s2['total_trades']} trades from prior session {s1.id}!"
        )
E       AssertionError: VULNERABILITY: Session sess_5f9371287131 leaked 1 trades from prior session sess_847b58d86f05!
E       assert 1 == 0

tests\test_m2_challenger_lifecycle.py:845: AssertionError
================= 1 failed, 15 deselected, 1 warning in 4.96s =================
```

### 1.3 Silent Dependency in Challenger Test 2
In `tests/test_m2_challenger_lifecycle.py`:
- `test_stress_session_isolation_and_no_telemetry_leakage` (line 832) explicitly sets `broker.active_session_id = s1.id`.
- `test_stress_compute_performance_accounting_accuracy` (lines 797–806) calls `mgr.start_session(session.id)` without passing `bot` and without setting `broker.active_session_id = session.id`.
- In `src/execution/broker.py:846`:
  ```python
  effective_session_id = session_id or getattr(self, "active_session_id", None)
  ```
  Because neither was provided, positions and closed trades were inserted with `session_id = NULL`.
- If an implementer removes the fallback in `compute_session_performance()` without adding auto-resolution in `PaperBroker` or setting `broker.active_session_id`, `test_stress_compute_performance_accounting_accuracy` fails with `AssertionError: assert 0 == 2`.

---

## 2. Logic Chain

1. **Step 1 (Root Cause)**: Observation 1.1 shows that when `closed_trades` is an empty list (`[]`), `if not closed_trades:` evaluates to `True`. The fallback query `SELECT * FROM trades WHERE account_id = ?` fetches all historical trades belonging to that account. Because sequential sessions on an account share the same `account_id`, Session 2 inherits trades and realized P&L from Session 1.
2. **Step 2 (Position Leakage)**: Observation 1.1 shows that `if not open_positions:` similarly falls back to `WHERE account_id = ?`. If Session 1 was stopped with `KEEP_OPEN`, Session 2 inherits open positions from Session 1 into its `invested_equity`, `unrealized_pnl`, and `open_positions_count`.
3. **Step 3 (Fix Design for Session Manager)**: Scoping queries strictly to `WHERE session_id = ?` eliminates cross-session data leakage:
   - When a session has 0 closed trades, `closed_trades = []`.
   - `total_trades = 0`, `winning_trades = 0`, `win_rate_pct = 0.0`, `realized_pnl = 0.0`.
   - `starting_capital = float(session.allocated_capital)`.
   - `current_cash = max(0.0, starting_capital + 0.0 - invested_equity) = starting_capital`.
   - `total_equity = starting_capital`.
4. **Step 4 (Fix Design for PaperBroker Auto-Resolution)**: From Observation 1.3, if `broker.active_session_id` is not manually set, `PaperBroker.open_position()` must defensively auto-resolve the active `RUNNING` session for `self.account_id` from the ledger database. This ensures all trades and positions opened during a running session are strictly tagged with that session ID, even in direct broker test scenarios.
5. **Step 5 (Empirical Verification)**: The test harness `verify_fix.py` proved that under the proposed blueprint:
   - Session 2 reports `total_trades = 0` and `realized_pnl = 0.0` (passing isolation).
   - Session 2 reports `open_positions_count = 0` despite Session 1 having a kept-open position.
   - Mixed accounting (wins, losses, open positions) calculates exact financial metrics without discrepancy.

---

## 3. Caveats

1. **Read-Only Investigation**: As instructed, no modifications were made to production source files (`src/execution/session_manager.py` or `src/execution/broker.py`). Implementation must be carried out by a remediation worker agent (`m2_worker_1`).
2. **Independent Concurrency TOCTOU Finding**: Challenger 1 also reported a race condition in `SessionManager.start_session()` (Defect 1). While that defect is separate from `compute_session_performance()`, both can be resolved in the same iteration without mutual interference.
3. **Database Contamination in Unisolated Tests**: Global FastAPI endpoints in `server.py` reference `data/trading_ledger.db`. If leftover sessions in `RUNNING` state exist from previous un-isolated scripts, tests using `TestClient(app)` will encounter `409 Conflict`. Unit and integration test suites should isolate their database files using `tmp_path`.

---

## 4. Conclusion

The cross-session telemetry leakage vulnerability in `compute_session_performance()` is completely diagnosed and reproducible.

### Blueprint for Remediation Worker:

#### 1. In `src/execution/session_manager.py` (lines 740–755):
Replace the fallback block with strict session-scoped queries:
```python
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

#### 2. In `src/execution/broker.py` (around line 846 in `open_position()`):
Add defensive session ID auto-resolution:
```python
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

#### 3. In `tests/test_m2_challenger_lifecycle.py` (line 798):
Add `broker.active_session_id = session.id` to match line 832.

---

## 5. Verification Method

### Step 1: Run Pre-Built Verification Test Harness
```powershell
Set-Location "C:\Users\Shivam\Desktop\trade_bot"
$env:PYTHONPATH = "."
py .agents\teamwork\m2_i2_explorer_2\verify_fix.py
```
**Expected Output**:
`ALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!`

### Step 2: Verify Challenger Lifecycle Suite After Applying Fix
```powershell
Set-Location "C:\Users\Shivam\Desktop\trade_bot"
py -m pytest tests/test_m2_challenger_lifecycle.py -v
```
**Passing Criteria**:
`test_stress_session_isolation_and_no_telemetry_leakage` must report `PASSED`.
`test_stress_compute_performance_accounting_accuracy` must report `PASSED`.

### Step 3: Run Full System Regression Suite
```powershell
Set-Location "C:\Users\Shivam\Desktop\trade_bot"
py -m pytest tests/test_trading_session_lifecycle.py tests/test_milestone_m2_sessions.py -v
```

### Invalidation Conditions:
- If a session with 0 trades reports `total_trades > 0` or `realized_pnl != 0.0`.
- If an unclosed position from a prior session appears in `open_positions` for a new session.
- If removing the fallback causes `test_stress_compute_performance_accounting_accuracy` to fail due to unpopulated `session_id`.
