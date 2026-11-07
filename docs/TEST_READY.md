# SYNAPSE-TITAN Test Readiness & Execution Manual (TEST_READY.md)

**Status:** APPROVED & TEST-READY  
**Author:** test_writer_e2e (E2E Test Suite Architect)  
**Target Repository:** `C:\Users\Shivam\Desktop\trade_bot`  
**Date:** 2026-11-04  

---

## 1. Readiness Certification Summary

The comprehensive Dual-Track Opaque-Box Test Suite has been created, verified, and audited against all technical specifications in `PROJECT.md` and `ORIGINAL_REQUEST.md`.

### Aggregate Quality Scorecard
| Test Suite / Target | Framework | Total Tests | Passed | Failed | Status |
|---|---|---|---|---|---|
| `tests/test_market_sessions.py` | Pytest (Python 3.13) | 35 | 35 | 0 | **PASS (100%)** |
| `tests/test_e2e_platform.py` | Pytest (Python 3.13) | 42 | 42 | 0 | **PASS (100%)** |
| `tests/test_phase1_phase2_fixes.py` | Python Script | 8 | 8 | 0 | **PASS (100%)** |
| `frontend/src/utils/ringBuffer.test.ts` | Vitest / Node.js | 6 | 6 | 0 | **PASS (100%)** |
| `frontend/` Production Build | Vite 5.4 + TSC | Build Target | 0 errors | 0 | **PASS (Clean)** |
| **Platform Total** | **Dual-Track** | **91 Tests** | **91** | **0** | **100% GREEN** |

---

## 2. Test Suite Catalog & Coverage Breakdown

### Suite 1: `tests/test_market_sessions.py` (35 Tests)
Validates the physical exchange calendar engine (`src/execution/market_sessions.py`) across four global asset classes:
- **`TestMarketTypeDetection` (5 tests)**:
  - Indian Equities detection (`.NS`, `.BO`, `^NSE`, `^BS`, case-insensitive).
  - US Equities detection (`NVDA`, `AAPL`, `TSLA`, `MSFT`, `AMD`).
  - Commodities detection (`GC=F`, `SI=F`, `CL=F`, `GLD`, `SLV`, `USO`).
  - Forex ECN detection (`EURUSD=X`, `GBPUSD=X`, `USDJPY=X`, `DX-Y.NYB`, `UUP`).
  - Cryptocurrencies detection (`BTC-USD`, `ETH-USD`, `SOL-USDT`, `BTC`, `ETH`, `DOGE`).
- **`TestNSEMarketSchedule` (9 tests)**:
  - Overnight `CLOSED` state (04:30 IST).
  - Pre-market `PRE_MARKET` order discovery (09:00–09:15 IST).
  - Regular trading hours `OPEN` (09:15–15:30 IST).
  - Post-market `POST_MARKET` closing price determination (15:30–16:00 IST).
  - After-hours `CLOSED` state (16:00–23:59 IST).
  - Weekend state transition (Saturday/Sunday -> Monday open).
  - Statutory holiday handling: Republic Day (2026-01-26).
  - Weekend precedence on weekend holidays (Independence Day 2026-08-15).
  - Exact boundary seconds: 09:14:59 (PRE), 09:15:00 (OPEN), 15:30:00 (OPEN), 15:30:01 (POST), 16:00:00 (POST), 16:00:01 (CLOSED).
- **`TestNYSEMarketSchedule` (8 tests)**:
  - Overnight `CLOSED` state (02:30 ET).
  - US Pre-market `PRE_MARKET` session (04:00–09:30 ET).
  - Regular trading hours `OPEN` (09:30–16:00 ET).
  - US After-hours `POST_MARKET` session (16:00–20:00 ET).
  - Statutory holidays: Martin Luther King Jr. Day (2026-01-19), Christmas Day (2026-12-25).
  - Exact boundary seconds: 09:29:59 (PRE), 09:30:00 (OPEN), 16:00:00 (OPEN), 16:00:01 (POST), 20:00:00 (POST), 20:00:01 (CLOSED).
  - Daylight Saving Time transitions: EDT summer open (13:30 UTC = 09:30 EDT) vs EST winter open (14:30 UTC = 09:30 EST).
- **`TestCommoditiesAndForexSchedules` (5 tests)**:
  - COMEX Gold (`GC=F`) Sunday pre-open (Sunday 17:15–18:00 ET).
  - Active session continuous trading (Tuesday 12:00 ET).
  - Daily maintenance pause (Mon–Thu 17:00–18:00 ET).
  - Weekend shutdown (Friday 17:00 ET to Sunday 17:15 ET).
  - Forex ECN 24/5 schedule (Sunday 17:00 ET to Friday 17:00 ET).
- **`TestCryptoContinuousSchedule` (5 tests)**:
  - Parameterized verification of 24/7/365 continuous trading across New Year's Day, Saturday midnight, Sunday afternoon, Christmas Day, and Leap Day.
- **`TestSimulationModeDecoupling` (2 tests)**:
  - Closed NSE stock in simulation mode: physical badge remains `WEEKEND`, but `is_tradable=True` and `tick_frozen=False`.
  - Holiday NYSE stock in simulation mode: physical badge remains `HOLIDAY`, trades allowed.
- **`TestTelemetrySerializationAndProperties` (1 test)**:
  - Validates `to_dict()` JSON payload structure, field types, and property aliases.

---

### Suite 2: `tests/test_e2e_platform.py` (42 Tests)
Validates the complete 4-tier acceptance hierarchy:

#### Tier 1: Feature Coverage (30 Tests)
- **Frontend Memory Stability & Bounded Buffers (5 tests)**:
  - `test_ring_buffer_bounded_capacity_and_fifo_eviction`: Ring buffer bounds, FIFO eviction when capacity reached.
  - `test_ring_buffer_zero_memory_leak_heavy_streaming`: Streaming 10,000 prices into 500-capacity buffer; zero unbounded growth.
  - `test_ring_buffer_peek_and_clear_invariants`: Tests `peek_latest`, `peek_oldest`, `clear`, `is_empty`, `is_full`.
  - `test_page_visibility_lifecycle_simulation`: Tab hidden (`document.hidden = true`) halts polling; wake-up resyncs without queue buildup.
  - `test_activity_log_bounded_at_100_entries`: Live bot activity log capped at 100 entries.
- **Physical Market Sessions (5 tests)**:
  - `test_nse_schedule_enforcement`: NSE Mumbai open vs closed.
  - `test_nyse_schedule_enforcement`: NYSE/NASDAQ open vs pre-market.
  - `test_comex_gold_schedule_enforcement`: Gold open vs daily pause.
  - `test_crypto_24_7_continuous_schedule`: Crypto continuous trading.
  - `test_forex_24_5_continuous_schedule`: Forex open vs weekend pause.
- **Price Freezing & Simulation Decoupling (5 tests)**:
  - `test_closed_market_price_freeze`: Closed assets skip price advances during `step_tick()`.
  - `test_simulation_mode_allows_synthetic_ticks_on_closed_markets`: `simulation_mode=True` allows synthetic price movement.
  - `test_crypto_ticks_continue_while_equities_frozen`: Mixed universe step advances Crypto while keeping Equities pinned.
  - `test_price_history_series_bounded_at_60_bars`: `price_series` capped at 60 bars.
  - `test_equity_comparison_series_bounded_at_60_bars`: `comparison_series` capped at 60 bars.
- **Pre-Market Pending Orders (5 tests)**:
  - `test_pre_market_order_insertion_with_soft_cash_hold`: Queueing pre-market order places soft hold on `reserved_cash`.
  - `test_available_cash_deduction_by_reserved_cash`: `available_cash == current_cash - reserved_cash`.
  - `test_cancel_pending_order_releases_cash`: Order cancellation releases reservation hold.
  - `test_pending_order_execution_on_market_open`: `execute_pending_orders_for_ticker` fills order and creates position.
  - `test_multiple_pending_orders_fifo_execution`: Queueing multiple orders drains in FIFO order on open.
- **Multi-Asset Monitoring & Controls (5 tests)**:
  - `test_multi_asset_watchlist_initialization`: Watchlist supports multi-asset catalog.
  - `test_dynamic_asset_arming_disarming`: Dynamic toggle of armed tickers via `update_asset_selection()`.
  - `test_custom_ticker_resolution_pipeline`: Custom symbol classification and session tracking.
  - `test_portfolio_mark_to_market_pnl_aggregation`: Unrealized/realized PnL aggregated across multi-asset positions.
  - `test_risk_guardrail_kelly_sizing`: CVaR-Kelly leverage ceiling enforcement.
- **Ingestion Pipeline & Cache (5 tests)**:
  - `test_base_market_data_provider_contract`: `LiveQuote` spread, spread_bps, and mid_price.
  - `test_dynamic_cache_ttl_intraday_vs_daily`: Intraday cache (1m) expires in 2m; daily cache (1d) valid for 24h.
  - `test_timezone_preservation_without_naive_stripping`: Historical timestamps preserve UTC timezone.
  - `test_downloader_cache_hit_latency`: Local disk cache read executes under 50ms.
  - `test_yfinance_provider_quote_generation`: `YFinanceProvider` conformance and connection state.

#### Tier 2: Boundary & Corner Cases (7 Tests)
- `test_boundary_exact_open_close_seconds`: Exactly 09:14:59 vs 09:15:00 IST; 09:29:59 vs 09:30:00 ET.
- `test_dst_boundary_us_equities`: Summer EDT (13:30 UTC) vs Winter EST (14:30 UTC).
- `test_statutory_holiday_transitions`: Holiday order queueing on Republic Day.
- `test_weekend_transition_cme_gold`: Friday 17:01 ET close -> Sunday 17:20 ET pre-open -> Sunday 18:01 ET open.
- `test_insufficient_unreserved_cash_order_rejection`: Attempting to queue order exceeding available cash raises `ValueError`.
- `test_double_cancellation_of_pending_order`: Cancelling an already cancelled order returns `False`.
- `test_zero_quantity_or_invalid_price_order`: Orders below $50 minimum threshold raise `ValueError`.

#### Tier 3: Cross-Feature Combinations (3 Tests)
- `test_order_submitted_on_holiday_persists_through_weekend_to_monday`: Order queued on Good Friday stays pending across Saturday/Sunday and executes Monday morning at 09:15 IST.
- `test_simultaneous_price_freeze_and_continuous_crypto`: Unified multi-asset step where NSE is frozen, Gold is halted for maintenance, and Crypto advances continuously.
- `test_simulation_mode_toggle_preserves_physical_session_badge`: Simulation mode enables synthetic trading while preserving physical exchange session telemetry.

#### Tier 4: Real-World Scenarios (2 Tests)
- `test_multi_asset_portfolio_execution`: Simultaneous buy orders across RELIANCE.NS (closed -> queued), NVDA (pre-market -> queued), and BTC-USD (open -> immediate fill).
- `test_tab_hidden_simulation_no_queue_buildup`: 50 background ticks during `document.hidden = true` result in zero client buffer buildup; tab wake-up performs a clean snapshot resync.

---

## 3. How to Run the Tests

### Command 1: Run All Automated Pytest Suites (77 Tests)
```powershell
cd C:\Users\Shivam\Desktop\trade_bot
py -m pytest tests/test_market_sessions.py tests/test_e2e_platform.py -v
```
**Expected Output:**
```
====================== 77 passed in 13.85s ======================
```

### Command 2: Run Quantitative & Microstructure Regression Suite (8 Tests)
```powershell
cd C:\Users\Shivam\Desktop\trade_bot
py tests/test_phase1_phase2_fixes.py
```
**Expected Output:**
```
=== ALL 8 PHASE 1, 2 & 3 MATHEMATICAL & MICROSTRUCTURE INVARIANTS VERIFIED ===
```

### Command 3: Run Frontend Unit Tests (Vitest)
```powershell
cd C:\Users\Shivam\Desktop\trade_bot\frontend
npm test
```
**Expected Output:**
```
 Test Files  1 passed (1)
      Tests  6 passed (6)
```

### Command 4: Build Frontend Production Bundle
```powershell
cd C:\Users\Shivam\Desktop\trade_bot\frontend
npm run build
```
**Expected Output:**
```
✓ built in ~4s
dist/index.html
dist/assets/index.css
dist/assets/index.js
```

---

## 4. Test Sign-Off & Release Approval

All criteria defined in `PROJECT.md` Milestones M1, M2, M3, and M4 have been verified:
- [x] Browser memory leak and freezing bug eliminated via bounded `RingBuffer<T>` and `usePageVisibility`.
- [x] Physical exchange session timing engine strictly enforced across NSE, NYSE, COMEX, Crypto, and Forex.
- [x] 6-state session machine (`OPEN`, `CLOSED`, `PRE_MARKET`, `POST_MARKET`, `WEEKEND`, `HOLIDAY`) with countdowns.
- [x] Price freeze active for closed markets; decoupled simulation mode override.
- [x] Pre-market pending order queueing in SQLite with soft cash holds and market open execution.
- [x] Multi-asset monitoring, custom ticker resolution, and dynamic arming.
- [x] Modular data provider architecture, dynamic TTL caching, and UTC timezone alignment.
- [x] 100% test pass rate across all tiers.
