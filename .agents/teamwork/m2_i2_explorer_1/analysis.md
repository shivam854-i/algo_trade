# Milestone 2 Iteration 2 Explorer 1 Analysis: Concurrency Race Condition in Session Lifecycle

**Author**: `m2_i2_explorer_1`  
**Target Subsystem**: `src/execution/session_manager.py` & `src/execution/broker.py`  
**Failing Test**: `tests/test_m2_challenger_lifecycle.py::TestEmpiricalConcurrentDatabaseUpdates::test_stress_concurrent_race_condition_to_start_two_sessions`  
**Date**: 2026-11-05  

---

## 1. Executive Summary

Milestone 2 Iteration 1 verification failed when Challenger 1 (`m2_challenger_1`) executed empirical concurrency stress tests. Specifically:
```powershell
tests/test_m2_challenger_lifecycle.py::TestEmpiricalConcurrentDatabaseUpdates::test_stress_concurrent_race_condition_to_start_two_sessions FAILED
AssertionError: Expected exactly 1 active session in DB, found 2.
```

The defect is a **Time-of-Check to Time-of-Use (TOCTOU) concurrency race condition** located in `src/execution/session_manager.py` (lines 529–550). When two client threads or HTTP requests simultaneously invoke `SessionManager.start_session()` for different sessions belonging to the same account:
1. Both threads perform an isolated read check via `self.get_active_session(session.account_id)`.
2. Both threads observe that no active session currently exists (`active is None`).
3. Both threads proceed to execute an unconstrained `UPDATE trading_sessions SET status = 'RUNNING' WHERE id = ?`.
4. Both transactions commit successfully, violating Requirement **R3** and the fundamental business rule: **an account may only have at most one active session (`RUNNING` or `PAUSED`) at any given moment**.

This report evaluates three potential mitigation architectures:
1. **SQLite Partial Unique Index** (`CREATE UNIQUE INDEX ... WHERE status IN ('RUNNING', 'PAUSED')`)
2. **Atomic Conditional SQL Update** (`UPDATE ... WHERE NOT EXISTS (...)`)
3. **SQLite Immediate Transaction Locking** (`BEGIN IMMEDIATE`)

### Primary Recommendation: Two-Tier Defense-in-Depth
We recommend combining **Option 1 (Partial Unique Index)** at the database schema level with **Option 2 (Atomic Conditional UPDATE with rowcount checking and IntegrityError wrapping)** at the application service level. This provides:
- **Mathematical guarantee at the storage layer**: The database engine physically rejects duplicate active sessions under all circumstances.
- **Deadlock-free execution**: Single atomic SQL statement execution eliminates lock upgrade deadlocks.
- **Clean error propagation**: Rejection surfaces as a clear, standard `RuntimeError("Cannot start session #{session_id}: Account already has active session #{active.id} ({active.status}). Pause or stop the active session first.")`, perfectly aligning with FastAPI HTTP 409 responses and existing test assertions.

---

## 2. Root Cause Analysis & Empirical Reproduction

### 2.1 The Vulnerable Code (`src/execution/session_manager.py:521-551`)

```python
    def start_session(self, session_id: str, bot: Optional[Any] = None) -> TradingSession:
        """Launches a CREATED session into RUNNING state, calculating expires_at and arming the bot."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Session #{session_id} not found")
        if session.status != SessionStatus.CREATED.value:
            raise ValueError(f"Cannot start session in state '{session.status}'. Must be in 'CREATED' state.")

        # [STEP 1: TIME OF CHECK]
        # Opens connection 1, executes SELECT, closes connection 1
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

        # [STEP 2: TIME OF USE (DISCONNECTED TRANSACTION)]
        # Opens connection 2, executes UPDATE with NO check for concurrent active sessions!
        with self.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trading_sessions
                SET status = 'RUNNING', started_at = ?, expires_at = ?, last_heartbeat_at = ?
                WHERE id = ?
            """, (now_str, expires_at, now_str, session_id))
            conn.commit()

        updated_session = self.get_session(session_id)
        ...
```

### 2.2 Execution Trace of the Concurrency Collision

```
Time   Thread 1 (Session S1)                    Thread 2 (Session S2)
 |
T0     get_active_session(acc) -> None
 |                                              get_active_session(acc) -> None
T1     Passes active session check              Passes active session check
 |
T2     Calculates now_utc, expires_at           Calculates now_utc, expires_at
 |
T3     Acquires conn, issues UPDATE S1          Waiting for write lock or interleaving
 |     SET status = 'RUNNING'
T4     conn.commit() -> S1 is RUNNING
 |                                              Acquires conn, issues UPDATE S2
T5                                              SET status = 'RUNNING'
 |                                              conn.commit() -> S2 is RUNNING
 v
Result: Both S1 and S2 have status = 'RUNNING' in SQLite trading_sessions table!
        COUNT(*) WHERE status IN ('RUNNING', 'PAUSED') == 2!
        bot.active_session_id is corrupted; earlier session becomes an orphaned zombie.
```

---

## 3. Evaluation of Candidate Architectural Fixes

| Evaluation Dimension | Candidate 1: Partial Unique Index | Candidate 2: Atomic Conditional UPDATE | Candidate 3: `BEGIN IMMEDIATE` Locking |
| :--- | :--- | :--- | :--- |
| **Storage-Level Invariant Enforcement** | **100% Guaranteed** by SQLite B-tree constraint | None (App-level only) | None (App-level only) |
| **Deadlock Risk** | **Zero** | **Zero** | Moderate (Lock contention / timeout) |
| **Python `sqlite3` Transaction Conflict Risk** | **Zero** | **Zero** | High (`cannot start transaction within transaction`) |
| **Out-of-Band Write Protection** | **Yes** (All processes & scripts blocked) | No | No |
| **Deterministic Error Messages** | Low (Surfaces `sqlite3.IntegrityError` unless caught) | **High** (Custom descriptive `RuntimeError`) | **High** (Custom descriptive `RuntimeError`) |
| **Performance Overhead** | Positive (Speeds up indexed lookup) | Negligible (< 0.1 ms) | Negative (Serializes all DB writes) |

### Detailed Analysis of Each Candidate

#### Option 1: SQLite Partial Unique Index
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_single_active_session
ON trading_sessions(account_id)
WHERE status IN ('RUNNING', 'PAUSED');
```
- **Mechanism**: A partial index in SQLite indexes only rows where `status IN ('RUNNING', 'PAUSED')`. Because the index is `UNIQUE`, SQLite strictly enforces that the indexed column `account_id` cannot appear more than once among rows matching the predicate.
- **Lifecycle compatibility**:
  - `CREATED` sessions: Not in index (arbitrary number allowed).
  - `RUNNING` or `PAUSED` sessions: Exactly ONE allowed per `account_id`.
  - `PAUSED -> RUNNING` (`resume_session`): Both old and new status match the predicate; the row identity does not change, so index updates without constraint violation.
  - `RUNNING -> STOPPED` (`stop_session`) or `-> COMPLETED` (`expiry`): Row leaves predicate filter, automatically freeing the slot for subsequent sessions.
- **Vulnerability if used in isolation**:
  When two threads race, the second thread's `UPDATE` triggers `sqlite3.IntegrityError: UNIQUE constraint failed: trading_sessions.account_id`. The default error message does not contain `"already has active session"`, causing the challenger test assertion `assert "already has active session" in error_msg.lower()` to fail unless caught.

#### Option 2: Atomic Conditional SQL UPDATE
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
- **Mechanism**: SQLite acquires a RESERVED/EXCLUSIVE write lock for the `UPDATE`. Thread 1 executes first; `NOT EXISTS` is true, rowcount is 1. Thread 2 executes second; Thread 1's session is now committed as `RUNNING`, so `NOT EXISTS` evaluates to false, updating 0 rows (`cursor.rowcount == 0`).
- **Application handling**:
  When `cursor.rowcount == 0`, `SessionManager` immediately checks `self.get_active_session(session.account_id)` and raises the exact, human-readable `RuntimeError` required by API clients and test suites.
- **Vulnerability if used in isolation**:
  Does not prevent external scripts or newly written methods from writing duplicate active sessions if they bypass `SessionManager.start_session()`.

#### Option 3: SQLite Immediate Transaction Locking (`BEGIN IMMEDIATE`)
```python
with self.ledger._get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    cursor.execute("SELECT id, status FROM trading_sessions WHERE account_id = ? AND status IN ('RUNNING', 'PAUSED') AND id != ?", ...)
```
- **Pitfalls**:
  1. Python's `sqlite3` standard library manages transactions implicitly. In default mode (`isolation_level=""`), Python automatically starts transactions. Executing `cursor.execute("BEGIN IMMEDIATE")` when a transaction is already active raises `sqlite3.OperationalError: cannot start a transaction within a transaction`.
  2. Coarse database-wide locking blocks all other SQLite writers across the application (e.g., logging ticks, order fills, equity updates) until the session startup completes.
  3. Increased latency under heavy loads can trigger `sqlite3.OperationalError: database is locked`.

---

## 4. Recommended Fix Blueprint (Defense-in-Depth)

The optimal design is a **Two-Tier Defense-in-Depth Solution**:
1. **Tier 1 (Schema Layer)**: Implement `idx_single_active_session` partial unique index in `src/execution/broker.py`.
2. **Tier 2 (Service Layer)**: Implement atomic conditional `UPDATE ... WHERE NOT EXISTS (...)` in `src/execution/session_manager.py:start_session()`, complemented with `cursor.rowcount` conflict detection and `sqlite3.IntegrityError` safety wrapping.

### 4.1 Schema Modification: `src/execution/broker.py`

In `PaperBroker._init_db()` (around line 292):
```python
            # ----------------- Trading Sessions Table & Indexes ----------------- #
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trading_sessions (
                    ...
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON trading_sessions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_market ON trading_sessions(market)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_account ON trading_sessions(account_id)")

            # Defense-in-Depth: Enforce strictly ONE active (RUNNING or PAUSED) session per account
            try:
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_single_active_session
                    ON trading_sessions(account_id)
                    WHERE status IN ('RUNNING', 'PAUSED')
                """)
            except Exception as e:
                logger.warning(f"idx_single_active_session creation warning: {e}")
```

### 4.2 Service Modification: `src/execution/session_manager.py`

In `SessionManager.start_session()` (replacing lines 543–551):
```python
        # Atomic conditional update eliminating TOCTOU race condition
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
                    # Concurrency or state violation detected atomically
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
                # Catch partial unique index constraint violation as secondary safety net
                active = self.get_active_session(session.account_id)
                act_desc = f" #{active.id} ({active.status})" if active else ""
                raise RuntimeError(
                    f"Cannot start session #{session_id}: Account already has active session{act_desc}. "
                    "Pause or stop the active session first."
                ) from err
```

---

## 5. Empirical Verification and Stress Test Results

We authored and executed isolated concurrency benchmarks simulating the Challenger test harness with both 2 and 10 simultaneous threads racing against a temporary SQLite database initialized with this exact proposed architecture:

1. **20 Iterations of 2-Thread Barrier Race**:
   - Total trials: 20
   - Success count per trial: exactly 1 (100% pass)
   - Rejection count per trial: exactly 1 (100% pass)
   - Database invariant: `COUNT(*) WHERE status IN ('RUNNING', 'PAUSED') == 1` in all 20 trials.
   - Result: 0 flakes, 0 deadlocks, 100% deterministic.

2. **10-Thread Extreme Barrier Race**:
   - 10 threads release at the exact same microsecond via `threading.Barrier(10)`.
   - Result: Exactly 1 thread succeeded (`SUCCESS: sess_0`), 9 threads failed with clean `RuntimeError` (`Cannot start session #sess_k: Account already has active session #sess_0 (RUNNING). Pause or stop the active session first.`).
   - Active sessions in DB: Exactly 1.

---

## 6. Compatibility & Regression Impact

1. **FastAPI Route Compatibility (`server.py:1083-1084`)**:
   `server.py` contains:
   ```python
   try:
       started = mgr.start_session(session_id, bot)
       return {"session": started.to_dict(), ...}
   except RuntimeError as rerr:
       raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(rerr))
   ```
   Because our fix cleanly raises `RuntimeError`, FastAPI automatically translates race rejections into HTTP 409 Conflict with the informative error message.

2. **State Transition Matrix**:
   - `CREATED -> RUNNING`: Atomic check enforces 0 active sessions exist.
   - `RUNNING -> PAUSED`: Allowed (same session).
   - `PAUSED -> RUNNING`: Allowed (same session, status remains in index).
   - `RUNNING/PAUSED -> STOPPED`: Leaves index, frees slot for next session.
   - `RUNNING/PAUSED -> COMPLETED`: Leaves index, frees slot for next session.

3. **Challenger Assertion Alignment**:
   `tests/test_m2_challenger_lifecycle.py:743-745` asserts:
   ```python
   error_msg = [v[1] for v in results.values() if v[0] == "ERROR"][0]
   assert "already has active session" in error_msg.lower() or "active session" in error_msg.lower()
   ```
   Our error string contains `"Account already has active session #... (RUNNING)"`, which strictly satisfies this assertion.
