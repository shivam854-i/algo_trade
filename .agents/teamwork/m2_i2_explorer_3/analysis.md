# Technical Analysis & Implementation Blueprint: Broker Session Tagging, Parameter Validation Consistency & Holistic Regression Verification

- **Author**: Milestone 2 Iteration 2 Explorer 3 (`m2_i2_explorer_3`)
- **Working Directory**: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_explorer_3`
- **Target Files**: `src/execution/broker.py`, `server.py`, `src/execution/session_manager.py`
- **Date**: 2026-11-05
- **Role**: Read-only Exploration & Architectural Blueprint

---

## 1. Executive Summary

During the Milestone 2 Iteration 1 verification gate, independent reviews by `m2_reviewer_1` and adversarial challenges by `m2_challenger_1` identified three critical areas for system hardening prior to Milestone 3 (Wizard UI and Bot Execution Dashboard Controls):

1. **Unpopulated `orders.session_id` in Broker Ledger**:
   Although SQLite non-destructive migrations successfully add `session_id TEXT` and index `idx_orders_session` to the `orders` table, `PaperBroker._record_order_event()` and `queue_pre_market_order()` in `src/execution/broker.py` omit `session_id` in their `INSERT INTO orders` SQL queries. Consequently, all executed and pending orders retain `session_id = NULL`.

2. **Parameter Validation & Documentation Alignment**:
   A documentation discrepancy occurred in the `m2_worker_1` handoff report stating capital floors were currency-differentiated (`USD: 100.0, INR: 5000.0`), whereas both `SessionManager.validate_session_parameters()` and `server.py` enforce a uniform floor of `1,000.0` and ceiling of `10,000,000.0`. In addition, `server.py:start_trading_session` invokes `mgr.get_active_session()` globally without passing `session.account_id`, causing spurious 409 Conflict errors when another account has an active session.

3. **Holistic Regression Verification Across 81 Tests**:
   A simultaneous regression suite combining all 22 lifecycle tests (`tests/test_trading_session_lifecycle.py`), 43 validation challenger tests (`tests/test_m2_challenger_validation.py`), and 16 lifecycle challenger tests (`tests/test_m2_challenger_lifecycle.py`) must pass cleanly without test pollution, race condition deadlocks, or cross-session telemetry leakage.

This document provides complete, actionable blueprints for the Worker to implement these enhancements cleanly.

---

## 2. Deep Dive: `orders` Table `session_id` Tagging in `PaperBroker`

### 2.1 Current State & Root Cause Analysis

In `src/execution/broker.py`:
- **Line 195 (`CREATE TABLE IF NOT EXISTS orders`)**:
  The base table schema created on new installations lacks `session_id TEXT`. It is only added later via an `ALTER TABLE` statement in `TradingLedgerDB._init_db()` (line 295).
- **Line 673 (`_record_order_event`)**:
  When orders are placed, filled, partially filled, or rejected, `_record_order_event()` executes:
  ```python
  cursor.execute("""
      INSERT INTO orders (
          account_id, ticker, direction, order_type, shares, price, limit_price,
          filled_shares, remaining_shares, allocated_capital, target_price, stop_price,
          submitted_at, created_at, status, fill_price, bid_price, ask_price,
          slippage_bps, fee_paid, market_timestamp, filled_at, executed_at, rejection_reason
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  """, ...)
  ```
  `session_id` is completely absent from the column list and values tuple.
- **Line 1624 (`queue_pre_market_order`)**:
  When pre-market orders are scheduled, `queue_pre_market_order()` executes:
  ```python
  cursor.execute("""
      INSERT INTO orders (
          account_id, ticker, direction, order_type, shares, price, limit_price,
          filled_shares, remaining_shares, allocated_capital,
          target_price, stop_price, submitted_at, created_at, status
      ) VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?, ?, ?, ?, 'PRE_MARKET_PENDING')
  """, ...)
  ```
  `session_id` is omitted here as well.
- **Lines 1252 & 1733 (Order Transitions to Positions)**:
  When a working limit order is filled (`evaluate_working_orders`) or a queued pre-market order executes upon open (`execute_pending_orders_for_ticker`), `self.open_position()` is called without passing the order's `session_id`.

### 2.2 Architectural Blueprint & Proposed Code Modifications

#### A. Native Table Definition (`src/execution/broker.py:195`)
Include `session_id TEXT` directly in the base `CREATE TABLE IF NOT EXISTS orders` statement, ensuring new databases instantiate the column immediately:
```python
# Before (Line 222)
            cancellation_reason TEXT,
            rejection_reason TEXT
        )

# After
            cancellation_reason TEXT,
            rejection_reason TEXT,
            session_id TEXT
        )
```

#### B. Update `_record_order_event` (`src/execution/broker.py:646`)
1. Add `session_id: Optional[str] = None` to the method signature.
2. Resolve the effective session ID:
   ```python
   effective_session_id = session_id or getattr(self, "active_session_id", None)
   ```
3. Add `session_id` to the `INSERT INTO orders` SQL statement.
4. Add `"session_id": effective_session_id` to the returned dictionary.

```python
# Blueprint for _record_order_event
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
    session_id: Optional[str] = None,  # <--- Added
) -> Dict[str, Any]:
    now_str = datetime.now(timezone.utc).isoformat()
    filled_at = now_str if status in ("FILLED", "PARTIALLY_FILLED") else None
    effective_session_id = session_id or getattr(self, "active_session_id", None)

    with self.ledger._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO orders (
                account_id, ticker, direction, order_type, shares, price, limit_price,
                filled_shares, remaining_shares, allocated_capital, target_price, stop_price,
                submitted_at, created_at, status, fill_price, bid_price, ask_price,
                slippage_bps, fee_paid, market_timestamp, filled_at, executed_at, rejection_reason,
                session_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            effective_session_id,  # <--- Passed into tuple
        ))
        order_num = cursor.lastrowid
        order_id_str = f"ORD-{order_num}"
        cursor.execute("UPDATE orders SET order_id = ? WHERE id = ?", (order_id_str, order_num))
        conn.commit()

    return {
        "id": order_num,
        "order_id": order_id_str,
        "account_id": self.account_id,
        "session_id": effective_session_id,  # <--- Returned in payload
        "ticker": ticker.upper(),
        "direction": direction.upper(),
        ...
    }
```

#### C. Update `queue_pre_market_order` (`src/execution/broker.py:1584`)
1. Add `session_id: Optional[str] = None` to `queue_pre_market_order`.
2. Resolve `effective_session_id = session_id or getattr(self, "active_session_id", None)`.
3. Add `session_id` to the `INSERT INTO orders` statement.
4. Include `"session_id": effective_session_id` in the returned dictionary.

```python
# Blueprint for queue_pre_market_order
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
    session_id: Optional[str] = None,  # <--- Added
) -> Dict[str, Any]:
    ...
    effective_session_id = session_id or getattr(self, "active_session_id", None)
    with self.ledger._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO orders (
                account_id, ticker, direction, order_type, shares, price, limit_price,
                filled_shares, remaining_shares, allocated_capital,
                target_price, stop_price, submitted_at, created_at, status, session_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?, ?, ?, ?, 'PRE_MARKET_PENDING', ?)
        """, (
            self.account_id, ticker, direction.upper(), order_type.upper(), shares, current_price,
            lim_p, shares, alloc_cap, tp, sp, now_str, now_str, effective_session_id
        ))
        order_num = cursor.lastrowid
        order_id_str = f"ORD-{order_num}"
        cursor.execute("UPDATE orders SET order_id = ? WHERE id = ?", (order_id_str, order_num))
        conn.commit()

    return {
        "id": order_num,
        "order_id": order_id_str,
        "account_id": self.account_id,
        "session_id": effective_session_id,  # <--- Added
        "ticker": ticker,
        ...
    }
```

#### D. Update `submit_order` (`src/execution/broker.py:914`)
Add `session_id: Optional[str] = None` to `submit_order()` and forward `session_id=session_id` to all `_record_order_event(...)` calls and `open_position(..., session_id=session_id)` calls.

#### E. Order-to-Position Lifecycle Propagation
- In `execute_pending_orders_for_ticker` (`src/execution/broker.py:1733`):
  ```python
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
      session_id=ord_row["session_id"] if "session_id" in ord_row.keys() else None,  # <--- Inherit
  )
  ```
- In `evaluate_working_orders` (`src/execution/broker.py:1252`):
  ```python
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
      session_id=row["session_id"] if "session_id" in row.keys() else None,  # <--- Inherit
  )
  ```

#### F. Query Helpers with `session_id` Scoping
Extend `get_pending_orders()` and `get_order_history()` to accept an optional `session_id: Optional[str] = None` filter:
```python
def get_pending_orders(self, ticker: Optional[str] = None, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with self.ledger._get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM orders WHERE account_id = ? AND status IN ('PRE_MARKET_PENDING', 'WORKING', 'PARTIALLY_FILLED')"
        params = [self.account_id]
        if ticker:
            query += " AND ticker = ?"
            params.append(ticker.upper())
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        query += " ORDER BY id ASC"
        cursor.execute(query, tuple(params))
        return [dict(r) for r in cursor.fetchall()]
```

---

## 3. Deep Dive: Parameter Validation Consistency

### 3.1 Capital Floor & Boundary Alignment

| Component | Minimum Capital | Maximum Capital | Non-positive | Status |
|---|---|---|---|---|
| `SessionManager.validate_session_parameters` | `1,000.0` | `10,000,000.0` | Raises `ValueError` | **Consistent** |
| `server.py:SessionCreateRequest.validate_capital_boundaries` | `1,000.0` | `10,000,000.0` | Raises `ValueError` | **Consistent** |
| `server.py:validate_capital_and_currency` | `1,000.0` | `10,000,000.0` | HTTP 400 Bad Request | **Consistent** |
| `test_m2_challenger_validation.py` | `< 1,000.0` rejected | `> 10,000,000.0` rejected | `<= 0.0` rejected | **Consistent** |
| `test_trading_session_lifecycle.py` | `100.0` rejected (< 1,000) | `25,000,000.0` rejected (> 10M) | `-500`, `0` rejected | **Consistent** |
| `m2_worker_1/handoff.md:63` | `USD: 100.0, INR: 5000.0` | Unspecified | Stated | **Documentation Discrepancy** |

**Conclusion & Resolution**:
The codebase and automated test suites are already unified on the uniform capital boundaries:
- **Floor**: `1,000.0` (in the currency matching the market: 1,000 INR for NSE; 1,000 USD for US/Crypto/FX/Commodities).
- **Ceiling**: `10,000,000.0`.
- **Strictly positive**: `capital > 0.0`.
The reference in `m2_worker_1/handoff.md` to `USD: 100.0, INR: 5000.0` was an authoring typo in the prose report. The Worker and all future handoffs should document the verified uniform rule: `[1,000.0, 10,000,000.0]`.

### 3.2 Currency & Jurisdiction Rules Summary
- `INDIAN_NSE` -> `currency == "INR"`. Allowed ticker suffixes: `.NS`, `.BO` (or recognized in `ASSET_CATALOG["INDIAN_NSE"]`).
- `US_EQUITIES` -> `currency == "USD"`. No punctuation suffixes (`.`, `=`, `-`).
- `CRYPTO` -> `currency == "USD"`. Allowed ticker suffixes: `-USD`, `-USDT` (or recognized crypto catalog).
- `COMMODITIES` -> `currency == "USD"`. Allowed ticker suffixes: `=F` or ETF symbols `GLD`, `SLV`, `USO`, `UNG`.
- `FOREX` -> `currency == "USD"`. Allowed ticker suffixes: `=X` or currency ETFs `DX-Y.NYB`, `UUP`.
- Basket size: `1 <= len(instruments) <= 20`. Duplicates strictly rejected.

### 3.3 Horizon & Duration Rules Summary
- Horizons: `"1h"`, `"1d"`, `"1wk"`. Synonyms (`"1 hour"`, `"daily"`, `"weekly"`) normalized via `normalize_horizon()`.
- Duration types: `"FIXED"`, `"CUSTOM"`, `"MANUAL_STOP"`.
- `"FIXED"` or `"CUSTOM"` requires `1 <= duration_minutes <= 10080` (1 week).
- `"MANUAL_STOP"` enforces `expires_at = None` and never auto-expires.

### 3.4 REST Endpoint Account Scoping Fix in `server.py`

#### Defect in `start_trading_session` (`server.py:1076`)
Currently, line 1076 does:
```python
active = mgr.get_active_session()  # <--- BUG: queries global table across all accounts
if active and active.id != session_id and active.status == "RUNNING":
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Another session '{active.id}' is currently RUNNING. Stop or pause it first.")
```
**Impact**: If an orphaned or concurrent session exists on another account (e.g., `RACE_TEST_ACC`), starting any session on `PAPER_DEFAULT` fails with HTTP 409 Conflict. Furthermore, it fails to check `PAUSED` sessions (whereas `SessionManager` forbids starting when an active session is `RUNNING` or `PAUSED`).

**Blueprint Fix**:
```python
# In server.py: start_trading_session
active = mgr.get_active_session(session.account_id)
if active and active.id != session_id and active.status in ("RUNNING", "PAUSED"):
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Another session '{active.id}' is currently {active.status} for account '{session.account_id}'. Stop or complete it first.",
    )
```

#### Defect in `get_active_trading_session` (`server.py:960`)
Currently, line 964 does `session = mgr.get_active_session()` without account scoping.
**Blueprint Fix**:
```python
@app.get("/api/sessions/active", tags=["Trading Sessions"])
def get_active_trading_session(account_id: Optional[str] = Query(None)):
    """Returns currently operational session (RUNNING or PAUSED) for the account or null."""
    mgr = _get_session_manager()
    session = mgr.get_active_session(account_id or "PAPER_DEFAULT")
    if session is None:
        return {"session": None}
    return {"session": session.to_dict()}
```

---

## 4. Deep Dive: Holistic Regression Verification Guidance

### 4.1 Root Causes of Existing Challenger Failures
Running the three test suites together currently yields 3 failures out of 81 tests:

1. `test_trading_session_lifecycle.py::TestFastAPISessionEndpoints::test_full_rest_session_lifecycle`:
   - Caused by `server.py:1076` calling `mgr.get_active_session()` without `session.account_id`, colliding with orphaned test sessions in `data/trading_ledger.db`.
   - Verified: When orphaned sessions on `RACE_TEST_ACC` were stopped, all 22 lifecycle tests passed with 0 failures (`22 passed in 13.44s`).
2. `test_m2_challenger_lifecycle.py::TestEmpiricalConcurrentDatabaseUpdates::test_stress_concurrent_race_condition_to_start_two_sessions`:
   - Caused by the TOCTOU race condition in `SessionManager.start_session()` (lines 529–550), where two threads check `get_active_session()` concurrently before issuing separate `UPDATE` queries.
3. `test_m2_challenger_lifecycle.py::TestEmpiricalEdgeCases::test_stress_session_isolation_and_no_telemetry_leakage`:
   - Caused by the metric fallback query in `SessionManager.compute_session_performance()` (lines 746–748 and 752–754), where a session with 0 trades falls back to querying all historical trades on `account_id`.

### 4.2 Unified Synthesis for the Worker

To achieve a 100% clean pass across all 81 tests simultaneously:

| Component | Target File | Line(s) | Fix Summary |
|---|---|---|---|
| **1. TOCTOU Mutex & Unique Constraint** | `src/execution/session_manager.py` | 360, 525–551 | Add thread mutex `self._lock = threading.Lock()` and acquire it across active check + status update in `start_session()`. Add partial unique index `idx_single_active_session` in SQLite. |
| **2. Telemetry Fallback Elimination** | `src/execution/session_manager.py` | 744–755 | Remove `if not closed_trades:` account fallback and `if not open_positions:` account fallback. Sessions with 0 trades must return 0 trades and $0.00 PnL. |
| **3. Broker Orders `session_id` Tagging** | `src/execution/broker.py` | 195, 646–708, 1584–1655 | Add `session_id` to `CREATE TABLE orders`, pass `session_id` into `_record_order_event` and `queue_pre_market_order`, and include in `INSERT INTO orders` SQL queries. |
| **4. Server Account Scoping** | `server.py` | 960–967, 1076–1078 | Scope `get_active_session(session.account_id)` in `start_trading_session` and `get_active_trading_session`. Check both `RUNNING` and `PAUSED`. |

### 4.3 Step-by-Step Test Execution Plan for Worker

After applying the changes, the Worker must execute tests in this exact order:

```powershell
Set-Location "C:\Users\Shivam\Desktop\trade_bot"

# Step 1: Run Lifecycle Challenger Suite (16 tests)
py -m pytest tests/test_m2_challenger_lifecycle.py -v
# Expected: 16 passed, 0 failed

# Step 2: Run Validation Challenger Suite (43 tests)
py -m pytest tests/test_m2_challenger_validation.py -v
# Expected: 43 passed, 0 failed

# Step 3: Run Full Lifecycle Suite (22 tests)
py -m pytest tests/test_trading_session_lifecycle.py -v
# Expected: 22 passed, 0 failed

# Step 4: Run All 3 Milestone 2 Session Suites Together (81 tests)
py -m pytest tests/test_trading_session_lifecycle.py tests/test_m2_challenger_validation.py tests/test_m2_challenger_lifecycle.py -v
# Expected: 81 passed, 0 failed

# Step 5: Run Milestone 2 Physical Market Acceptance Suite (5 tests)
py -m pytest tests/test_milestone_m2_sessions.py -v
# Expected: 5 passed, 0 failed

# Step 6: Full Platform Regression Suite (245+ tests)
py -m pytest -q
# Expected: 245+ passed, 0 failed
```

---

## 5. Summary of Deliverables
- **Analysis**: Complete architectural blueprint documented above in `analysis.md`.
- **Handoff**: Formal 5-component report prepared in `handoff.md`.
- **Next Action**: Notify Lead Orchestrator to dispatch `m2_worker_1` for implementation.
