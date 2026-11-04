# SYNAPSE-TITAN Test Infrastructure Architecture (TEST_INFRA.md)

## 1. Executive Overview

The SYNAPSE-TITAN platform employs a **Dual-Track Opaque-Box Test Architecture** designed to validate quantitative models, high-frequency execution pipelines, database ledgers, physical exchange session timing engines, and modern component-based frontends.

The testing architecture guarantees:
1. **Mathematical Invariant Preservation**: Rigorous checks for fractional differentiation memory, causal HMM future-invariance, asymmetric CVaR-Kelly leverage ceilings, and friction modeling.
2. **Physical Market Session Compliance**: Second-precise validation of multi-jurisdiction trading hours (NSE/BSE, NYSE/NASDAQ, CME COMEX Gold, Forex, Crypto 24/7), dynamic Daylight Saving Time (DST) switches, and statutory holiday calendars.
3. **Execution Safety & Ledger Concurrency**: Deterministic pre-market order queueing (`PRE_MARKET_PENDING`), soft capital reservations (`reserved_cash`), and market-open FIFO execution.
4. **Memory Stability & Zero Browser Leaks**: Elimination of heap runaway via bounded $O(1)$ client circular buffers (`RingBuffer<T>`) and tab suspension via the Page Visibility API (`document.hidden`).

---

## 2. Dual-Track Testing Topology

The test suite is structured across two synchronized runtime tracks:

```
                                  SYNAPSE-TITAN
                                 TEST INFRASTRUCTURE
                                          │
            ┌─────────────────────────────┴─────────────────────────────┐
            ▼                                                           ▼
     TRACK A: PYTEST CORE                                    TRACK B: VITEST FRONTEND
   (Backend & E2E Suite)                                       (Cockpit Toolchain)
            │                                                           │
   ├── test_market_sessions.py                                 ├── ringBuffer.test.ts
   ├── test_e2e_platform.py                                    └── usePageVisibility hooks
   └── test_phase1_phase2_fixes.py                             └── lightweight-charts lifecycle
```

### Track A: Python / Pytest Engine & E2E Suite
- **Framework**: `pytest >= 8.0` with `anyio` and `zoneinfo` under Python 3.13.
- **Coverage**:
  - `tests/test_market_sessions.py` (35 tests): Exhaustive testing of `MarketCalendarManager`, `MarketSessionInfo`, market state transitions, holiday schedules, DST shifts, and second-by-second countdowns.
  - `tests/test_e2e_platform.py` (42 tests): Dual-track end-to-end integration covering 4 tiers:
    - Tier 1: Core feature coverage across memory bounds, physical sessions, price freeze, pre-market queues, multi-asset monitoring, and provider caching.
    - Tier 2: Boundary conditions, exact boundary seconds, statutory holidays, weekend transitions, zero-quantity orders, and capital limits.
    - Tier 3: Complex multi-system combinations (e.g., holiday order persistence through weekends to Monday open).
    - Tier 4: Real-world operational scenarios (multi-asset simultaneous portfolio execution, browser tab hidden simulation).
  - `tests/test_phase1_phase2_fixes.py` (8 tests): Quantitative mathematical invariants (FracDiff, HMM, Triple Barrier, HRP, statutory frictions, TCN pinball loss, microstructure gates).

### Track B: TypeScript / Vitest Frontend Suite
- **Framework**: `vitest >= 2.1` + TypeScript 5.6 + Vite 5.4 in `frontend/`.
- **Coverage**:
  - `frontend/src/utils/ringBuffer.test.ts` (6 tests): Validates $O(1)$ bounds, zero heap growth under high-frequency push, chronological FIFO eviction, and clearing semantics.
  - Page Visibility API lifecycle hooks: Verification that background tabs (`document.hidden === true`) suspend `setInterval` polling and canvas chart rendering.

---

## 3. Test Tier Architecture

The test suite adheres to a 4-tier testing hierarchy:

| Tier | Focus | Description | Test Count |
|---|---|---|---|
| **Tier 1** | **Feature Coverage** | Validates happy-path and core requirements (R1: memory bounds, R2: session enforcement, R3: multi-asset controls, R4: data ingestion). Minimum 5 test cases per feature. | 30 tests |
| **Tier 2** | **Boundary & Corner Cases** | Stress-tests exact boundary seconds (09:14:59 vs 09:15:00), DST shifts (EDT vs EST), statutory holidays, zero-quantity orders, negative prices, and cash exhaustion. | 7 tests |
| **Tier 3** | **Cross-Feature Combinations** | Evaluates multi-subsystem interactions: holiday orders surviving weekends to Monday open, simultaneous stock price freeze with 24/7 crypto streaming, and simulation mode decoupling. | 3 tests |
| **Tier 4** | **Real-World Scenarios** | Complex realistic workloads: multi-asset simultaneous portfolio execution (closed stock + pre-market stock + open crypto) and background tab hidden simulation without queue buildup. | 2 tests |

---

## 4. Isolation & Virtualization Mechanics

### 4.1 Temporal Virtualization (Time Travel)
To avoid polluting or modifying the host operating system's wall-clock time, all session timing and calendar routines accept an explicit `now_utc: Optional[datetime] = None` argument:
```python
# Evaluates market status at an exact historical or future UTC instant
sess = calendar.get_session_info("RELIANCE.NS", now_utc=datetime(2026, 1, 26, 5, 30, tzinfo=timezone.utc))
assert sess.state == MarketState.HOLIDAY
assert sess.holiday_name == "Republic Day"
```
When `now_utc` is omitted, the engine defaults to `datetime.now(timezone.utc)`.

### 4.2 SQLite Ledger Sandbox Isolation
Tests interacting with `TradingLedgerDB` or `PaperBroker` must never write to or alter the production ledger at `data/trading_ledger.db`. The test suite uses pytest's built-in `tmp_path` fixture to spin up ephemeral, per-test databases:
```python
@pytest.fixture
def isolated_db(tmp_path: Path) -> TradingLedgerDB:
    db_file = tmp_path / "test_trading_ledger.db"
    return TradingLedgerDB(db_path=db_file)
```
Each test executes against an isolated ledger with guaranteed state cleanliness and zero cross-test interference.

### 4.3 Ingestion Cache Sandbox Isolation
Downloader and provider tests create dedicated temporary cache directories (`tmp_path`) to verify cache expiration and TTL mechanics without affecting production cached CSVs in `data/cache`.

---

## 5. Execution Commands & Verification Guide

### 5.1 Full Test Suite Execution (All 77 Tests)
To execute the complete platform test suite with verbose output:
```powershell
cd C:\Users\Shivam\Desktop\trade_bot
py -m pytest tests/test_market_sessions.py tests/test_e2e_platform.py -v
```

### 5.2 Market Sessions Test Suite Only (35 Tests)
```powershell
cd C:\Users\Shivam\Desktop\trade_bot
py -m pytest tests/test_market_sessions.py -v
```

### 5.3 E2E Integration Suite Only (42 Tests)
```powershell
cd C:\Users\Shivam\Desktop\trade_bot
py -m pytest tests/test_e2e_platform.py -v
```

### 5.4 Quantitative & Microstructure Regression Suite (8 Invariants)
```powershell
cd C:\Users\Shivam\Desktop\trade_bot
py tests/test_phase1_phase2_fixes.py
```

### 5.5 Frontend Vitest Suite (Track B)
```powershell
cd C:\Users\Shivam\Desktop\trade_bot\frontend
npm test
```

### 5.6 Frontend Production Build Verification
```powershell
cd C:\Users\Shivam\Desktop\trade_bot\frontend
npm run build
```

---

## 6. Continuous Integration (CI) Quality Gates

Every CI build and production release must pass 100% of the following gates:
1. `tests/test_market_sessions.py` passes 35/35 tests (0 failures).
2. `tests/test_e2e_platform.py` passes 42/42 tests (0 failures).
3. `tests/test_phase1_phase2_fixes.py` reports `ALL 8 PHASE 1, 2 & 3 MATHEMATICAL & MICROSTRUCTURE INVARIANTS VERIFIED`.
4. `frontend/` passes `npm test` (6/6 tests passing) and `npm run build` generates clean assets in `dist/`.
