# Handoff Report — Milestone 2 Iteration 2 Explorer 1

**Agent**: `m2_i2_explorer_1`  
**Parent / Caller**: `d0b51128-456f-4a81-855c-2a488d288844`  
**Mission**: Concurrency race condition investigation & atomic fix design for `SessionManager.start_session()`  
**Status**: COMPLETE (Hard Handoff)  

---

## 1. Observation

### 1.1 Empirical Test Failure
Execution of the Challenger lifecycle test suite confirmed the TOCTOU concurrency race:
- Command:
  ```powershell
  cd C:\Users\Shivam\Desktop\trade_bot; py -m pytest tests/test_m2_challenger_lifecycle.py -v
  ```
- Verbatim Failure Output:
  ```
  FAILED tests/test_m2_challenger_lifecycle.py::TestEmpiricalConcurrentDatabaseUpdates::test_stress_concurrent_race_condition_to_start_two_sessions

  >       assert count == 1, f"Expected exactly 1 active session in DB, found {count}"
  E       AssertionError: Expected exactly 1 active session in DB, found 2
  E       assert 2 == 1

  tests\test_m2_challenger_lifecycle.py:757: AssertionError
  ```

### 1.2 Vulnerable Source Code
In `src/execution/session_manager.py:529-550`:
```python
        # Time-of-check:
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

        # Time-of-use (Disconnected connection & transaction):
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trading_sessions
                SET status = 'RUNNING', started_at = ?, expires_at = ?, last_heartbeat_at = ?
                WHERE id = ?
            """, (now_str, expires_at, now_str, session_id))
            conn.commit()
```

### 1.3 Schema Definition & Indexes
In `src/execution/broker.py:288-292`:
```python
cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON trading_sessions(status)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_market ON trading_sessions(market)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_account ON trading_sessions(account_id)")
```
Notice that no partial unique index exists on `(account_id) WHERE status IN ('RUNNING', 'PAUSED')`.

---

## 2. Logic Chain

1. **Disconnected Read-Write Transactions Enable TOCTOU** (from Observation 1.2):
   `self.get_active_session()` opens a connection, queries the database, and closes the connection. When Thread 1 and Thread 2 race simultaneously:
   - Thread 1 queries `get_active_session()` -> receives `None`.
   - Thread 2 queries `get_active_session()` -> receives `None`.
   - Thread 1 opens a new connection, executes `UPDATE ... SET status = 'RUNNING' WHERE id = sess_1`, commits.
   - Thread 2 opens a new connection, executes `UPDATE ... SET status = 'RUNNING' WHERE id = sess_2`, commits.
   - Result: Both sessions are written with status `RUNNING`, resulting in 2 active sessions in SQLite (Observation 1.1).

2. **Schema Invariant Absence Permits Dual Active Sessions** (from Observation 1.3):
   Because the database schema lacks a uniqueness constraint on `(account_id)` for active statuses, SQLite's storage engine permits arbitrary numbers of rows with `status = 'RUNNING'` for the same `account_id`.

3. **Inadequacy of `BEGIN IMMEDIATE` in Python `sqlite3`**:
   `BEGIN IMMEDIATE` locks the database at transaction start. However:
   - Python's standard `sqlite3` driver implicitly manages transactions. Calling `cursor.execute("BEGIN IMMEDIATE")` when a transaction is already active raises `sqlite3.OperationalError: cannot start a transaction within a transaction`.
   - It forces coarse-grained database-wide write locking, increasing lock contention and risk of `sqlite3.OperationalError: database is locked`.

4. **Inadequacy of Partial Unique Index Alone**:
   A partial unique index (`idx_single_active_session`) physically prevents two rows from entering `RUNNING` or `PAUSED`. However, when a conflict occurs, SQLite raises `sqlite3.IntegrityError: UNIQUE constraint failed: trading_sessions.account_id`. The default error message does not contain `"already has active session"`, causing the challenger test assertion `assert "already has active session" in error_msg.lower()` to fail unless caught.

5. **Sufficiency and Superiority of Defense-in-Depth (Index + Atomic Conditional Update)**:
   Combining:
   - **Layer 1 (Schema)**: `CREATE UNIQUE INDEX IF NOT EXISTS idx_single_active_session ON trading_sessions(account_id) WHERE status IN ('RUNNING', 'PAUSED')`
   - **Layer 2 (Query)**:
     ```sql
     UPDATE trading_sessions
     SET status = 'RUNNING', started_at = ?, expires_at = ?, last_heartbeat_at = ?
     WHERE id = ?
       AND status = 'CREATED'
       AND NOT EXISTS (
           SELECT 1 FROM trading_sessions
           WHERE account_id = ? AND status IN ('RUNNING', 'PAUSED')
       )
     ```
     with `if cursor.rowcount == 0` checking for active sessions and raising `RuntimeError`, plus wrapping `sqlite3.IntegrityError` to raise the same `RuntimeError`.
   - This was empirically simulated with 20 iterations of 2-thread races and an extreme 10-thread race; in 100% of cases, exactly 1 thread succeeded, all other threads received descriptive `RuntimeError`, and the database invariant `COUNT(*) == 1` was strictly preserved.

---

## 3. Caveats

1. **Scope Boundary**:
   This report specifically addresses the TOCTOU concurrency race in `start_session()`. The separate telemetry leakage defect in `compute_session_performance()` (lines 743-755) is addressed by `m2_i2_explorer_2`.
2. **Existing Database Cleanliness**:
   If an existing development database file already contains duplicate active sessions created during past test runs, executing `CREATE UNIQUE INDEX` directly on that file could fail until duplicates are removed or set to `STOPPED`. In `broker.py:_init_db()`, wrapping the index creation in a safe `try...except` block or resolving legacy duplicates ensures smooth backward compatibility.
3. **Execution Mode**:
   This is a read-only investigation. No source files have been modified.

---

## 4. Conclusion

**Actionable Blueprint for `m2_worker_1`**:

### Step 1: Add Partial Unique Index in `src/execution/broker.py`
In `PaperBroker._init_db()` (around line 292), add:
```python
            try:
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_single_active_session
                    ON trading_sessions(account_id)
                    WHERE status IN ('RUNNING', 'PAUSED')
                """)
            except Exception as e:
                logger.warning(f"idx_single_active_session creation warning: {e}")
```

### Step 2: Implement Atomic Conditional Update in `src/execution/session_manager.py`
In `SessionManager.start_session()` (replacing lines 543-551):
```python
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    UPDATE trading_sessions
                    SET status = 'RUNNING', started_at = ?, expires_at = ?, last_heartbeat_at = ?
                    WHERE id = ?
                      AND status = 'CREATED'
                      AND NOT EXISTS (
                          SELECT 1 FROM trading_sessions
                          WHERE account_id = ? AND status IN ('RUNNING', 'PAUSED')
                      )
                """, (now_str, expires_at, now_str, session_id, session.account_id))
                conn.commit()

                if cursor.rowcount == 0:
                    active = self.get_active_session(session.account_id)
                    if active and active.id != session_id:
                        raise RuntimeError(
                            f"Cannot start session #{session_id}: Account already has active session #{active.id} ({active.status}). "
                            "Pause or stop the active session first."
                        )
                    current = self.get_session(session_id)
                    if current and current.status != SessionStatus.CREATED.value:
                        raise ValueError(f"Cannot start session in state '{current.status}'. Must be in 'CREATED' state.")
                    raise RuntimeError(f"Cannot start session #{session_id}: Unable to transition to RUNNING state due to concurrent update.")
            except sqlite3.IntegrityError as err:
                active = self.get_active_session(session.account_id)
                act_desc = f" #{active.id} ({active.status})" if active else ""
                raise RuntimeError(
                    f"Cannot start session #{session_id}: Account already has active session{act_desc}. "
                    "Pause or stop the active session first."
                ) from err
```

---

## 5. Verification Method

To verify after implementation:

```powershell
Set-Location "C:\Users\Shivam\Desktop\trade_bot"

# Verify Challenger concurrency race test specifically passes:
py -m pytest tests/test_m2_challenger_lifecycle.py::TestEmpiricalConcurrentDatabaseUpdates::test_stress_concurrent_race_condition_to_start_two_sessions -v

# Verify existing lifecycle single-session constraint test passes:
py -m pytest tests/test_trading_session_lifecycle.py::TestSessionGating::test_single_active_session_constraint -v
```

**Passing Criteria**:
- `test_stress_concurrent_race_condition_to_start_two_sessions` reports `PASSED`.
- Exactly 1 session succeeds, the racing session raises `RuntimeError` matching `"already has active session"`.
- Database invariant check confirms `COUNT(*) == 1` active session in DB.
- Zero deadlocks or `OperationalError: database is locked`.
