# Handoff Report — Milestone 2 Empirical Challenger 1

**Verdict**: **`REQUEST_CHANGES`**

---

## 1. Observation

A dedicated empirical challenge test suite was authored in `tests/test_m2_challenger_lifecycle.py` containing 16 rigorous, adversarial stress tests covering all lifecycle state machine behaviors, time dilation, expiry policies, single active session constraints, multithreaded SQLite operations, and session isolation.

The test suite was executed from repository root `C:\Users\Shivam\Desktop\trade_bot`:
```powershell
py -m pytest tests/test_m2_challenger_lifecycle.py -v
```

### Execution Output Summary
```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\Shivam\Desktop\trade_bot
collected 16 items

tests/test_m2_challenger_lifecycle.py::TestEmpiricalRapidStateTransitions::test_stress_rapid_state_transitions_full_lifecycle PASSED [  6%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalRapidStateTransitions::test_stress_rapid_oscillating_pause_resume_50_iterations PASSED [ 12%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalRapidStateTransitions::test_stress_invalid_state_transition_matrix PASSED [ 18%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalTimeDilation::test_stress_time_dilation_exact_90min_offset PASSED [ 25%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalTimeDilation::test_stress_time_dilation_multiple_pauses_cumulative PASSED [ 31%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalExpiryPolicy::test_stress_expiry_policy_close_all PASSED [ 37%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalExpiryPolicy::test_stress_expiry_policy_keep_open PASSED [ 43%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalExpiryPolicy::test_stress_manual_stop_policy_close_all_vs_keep_open PASSED [ 50%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalSingleActiveSessionEnforcement::test_stress_single_active_session_rejection_when_running PASSED [ 56%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalSingleActiveSessionEnforcement::test_stress_single_active_session_rejection_when_paused PASSED [ 62%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalSingleActiveSessionEnforcement::test_stress_single_active_session_allowed_after_terminal_states PASSED [ 68%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalConcurrentDatabaseUpdates::test_stress_concurrent_sqlite_updates_multithreading PASSED [ 75%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalConcurrentDatabaseUpdates::test_stress_concurrent_race_condition_to_start_two_sessions FAILED [ 81%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalEdgeCases::test_stress_manual_stop_session_never_auto_expires PASSED [ 87%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalEdgeCases::test_stress_compute_performance_accounting_accuracy PASSED [ 93%]
tests/test_m2_challenger_lifecycle.py::TestEmpiricalEdgeCases::test_stress_session_isolation_and_no_telemetry_leakage FAILED [100%]

================================== FAILURES ===================================
_ TestEmpiricalConcurrentDatabaseUpdates.test_stress_concurrent_race_condition_to_start_two_sessions _
...
>           assert count == 1, f"Expected exactly 1 active session in DB, found {count}"
E           AssertionError: Expected exactly 1 active session in DB, found 2
E           assert 2 == 1

tests\test_m2_challenger_lifecycle.py:757: AssertionError

_ TestEmpiricalEdgeCases.test_stress_session_isolation_and_no_telemetry_leakage _
...
>       assert perf_s2["total_trades"] == 0, (
            f"VULNERABILITY: Session {s2.id} leaked {perf_s2['total_trades']} trades from prior session {s1.id}!"
        )
E       AssertionError: VULNERABILITY: Session sess_2c4db634f817 leaked 1 trades from prior session sess_ea8cde700967!
E       assert 1 == 0

tests\test_m2_challenger_lifecycle.py:845: AssertionError
================== 2 failed, 14 passed, 1 warning in 13.31s ===================
```

---

## 2. Logic Chain

### Defect 1: Time-Of-Check to Time-Of-Use (TOCTOU) Race Condition in `SessionManager.start_session()`
- **Location**: `src/execution/session_manager.py:529-550`
- **Observation**:
  ```python
  active = self.get_active_session(session.account_id)
  if active and active.id != session_id:
      raise RuntimeError(
          f"Cannot start session #{session_id}: Account already has active session #{active.id} ({active.status}). "
          "Pause or stop the active session first."
      )
  ...
  with self.ledger._get_connection() as conn:
      cursor = conn.cursor()
      cursor.execute("""
          UPDATE trading_sessions
          SET status = 'RUNNING', started_at = ?, expires_at = ?, last_heartbeat_at = ?
          WHERE id = ?
      """, (now_str, expires_at, now_str, session_id))
      conn.commit()
  ```
- **Inference**:
  `get_active_session()` opens a connection, queries the database, and closes the connection.
  When two threads or concurrent API callers submit `start_session` at the same time:
  1. Thread 1 executes `get_active_session()`: finds no active session (`active is None`).
  2. Thread 2 executes `get_active_session()`: finds no active session (`active is None`).
  3. Thread 1 executes `UPDATE trading_sessions SET status = 'RUNNING' WHERE id = sess_1` and commits.
  4. Thread 2 executes `UPDATE trading_sessions SET status = 'RUNNING' WHERE id = sess_2` and commits.
  5. **Result**: Both sessions successfully enter `RUNNING` status in SQLite. The database contains 2 simultaneous active sessions for the same account. `bot.active_session_id` is corrupted, and the earlier session becomes an untracked zombie session.
- **Remediation**:
  Wrap session activation in an immediate transaction or Python mutex, or use an atomic conditional SQL update:
  ```python
  with self.ledger._get_connection() as conn:
      cursor = conn.cursor()
      cursor.execute("BEGIN IMMEDIATE")
      cursor.execute(
          "SELECT id FROM trading_sessions WHERE account_id = ? AND status IN ('RUNNING', 'PAUSED') AND id != ?",
          (session.account_id, session_id),
      )
      conflict = cursor.fetchone()
      if conflict:
          conn.rollback()
          raise RuntimeError(f"Cannot start session #{session_id}: Account already has active session #{conflict['id']}.")
      cursor.execute("""
          UPDATE trading_sessions
          SET status = 'RUNNING', started_at = ?, expires_at = ?, last_heartbeat_at = ?
          WHERE id = ?
      """, (now_str, expires_at, now_str, session_id))
      conn.commit()
  ```

---

### Defect 2: Performance Telemetry & P&L Cross-Session Data Leakage in `SessionManager.compute_session_performance()`
- **Location**: `src/execution/session_manager.py:743-755`
- **Observation**:
  ```python
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
- **Inference**:
  When a user creates and launches a new session (e.g. Session 2) on an account that had previously completed trades or positions in Session 1:
  1. Session 2 has 0 closed trades initially.
  2. The primary query `SELECT * FROM trades WHERE session_id = ?` correctly returns 0 rows.
  3. The `if not closed_trades:` condition triggers!
  4. It executes `SELECT * FROM trades WHERE account_id = ?` and loads ALL historical trades from Session 1!
  5. It computes win rate, profit factor, total trades, and realized P&L from Session 1 and displays them on Session 2's dashboard telemetry!
  6. Exactly the same bug occurs for `open_positions`: an empty session inherits open positions from previous sessions if unclosed.
  7. **Result**: Complete breach of session isolation and ledger partition boundaries.
- **Remediation**:
  Remove the unconstrained fallback to `account_id`. A session's performance must ONLY reflect trades and positions tagged with its `session_id`. If legacy un-tagged trades must be supported, restrict the fallback exclusively to records where `session_id IS NULL` when inspecting a default unassigned session:
  ```python
  cursor.execute("SELECT * FROM trades WHERE session_id = ?", (session_id,))
  closed_trades = cursor.fetchall()

  cursor.execute("SELECT * FROM positions WHERE status = 'OPEN' AND session_id = ?", (session_id,))
  open_positions = cursor.fetchall()
  ```

---

## 3. Caveats
- Sequential lifecycle actions without concurrency race conditions work as expected:
  - Rapid state transitions (`CREATED -> RUNNING -> PAUSED -> RESUMED -> STOPPED`) pass cleanly.
  - Time dilation is mathematically exact: a 1-hour session paused for 30 minutes expires exactly 90 minutes after start.
  - Expiry policies (`CLOSE_ALL` vs `KEEP_OPEN`) properly flatten or preserve positions on expiry.
  - Sequential single-session checks properly return `RuntimeError` and HTTP 409 Conflict.
  - Multi-threaded concurrent writes to `update_session_metrics()` and reads do not lock SQLite when no state violation occurs.
- The two failures identified are genuine production vulnerabilities that occur under concurrent execution or sequential session execution on the same account.

---

## 4. Conclusion

**Verdict: `REQUEST_CHANGES`**

Milestone 2 cannot be approved in its current state because:
1. `SessionManager.start_session()` allows concurrent active sessions for the same account under simultaneous race conditions, violating R3 and the single active session constraint.
2. `SessionManager.compute_session_performance()` leaks historical trades, win rates, and realized P&L across sessions due to an invalid `if not closed_trades` fallback to `account_id`.

The implementer (`m2_worker_1`) must apply the two atomic and query isolation fixes specified in Section 2.

---

## 5. Verification Method

To independently verify the empirical challenge results:
```powershell
Set-Location "C:\Users\Shivam\Desktop\trade_bot"
py -m pytest tests/test_m2_challenger_lifecycle.py -v
```

**Passing Criteria after Fix**:
All 16 test cases in `tests/test_m2_challenger_lifecycle.py` must report `PASSED` (16 passed in ~13s), with 0 failures and 0 errors.
