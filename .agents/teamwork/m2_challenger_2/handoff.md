# Handoff Report — Milestone 2 Empirical Challenger 2

**Verdict**: **`APPROVE`**

---

## 1. Observation

### Empirical Challenge Suite Authored
A dedicated empirical challenge test file was authored at:
`C:\Users\Shivam\Desktop\trade_bot\tests\test_m2_challenger_validation.py` (520 lines, 43 test cases across 6 challenge classes).

### Test Execution Command & Verbatim Result
Executed via command from `C:\Users\Shivam\Desktop\trade_bot`:
```powershell
py -m pytest tests/test_m2_challenger_validation.py -v
```

Output:
```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.2.0, pluggy-1.7.0 -- C:\Users\Shivam\AppData\Local\Programs\Python\Python313\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\Shivam\Desktop\trade_bot
plugins: anyio-4.13.0, platformdirs-4.13.5
collecting ... collected 43 items

tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_negative_and_zero[-1.0] PASSED [  2%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_negative_and_zero[-500.0] PASSED [  4%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_negative_and_zero[-10000.0] PASSED [  6%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_negative_and_zero[0.0] PASSED [  9%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_negative_and_zero[-0.0001] PASSED [ 11%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_below_minimum_threshold[0.01] PASSED [ 13%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_below_minimum_threshold[100.0] PASSED [ 16%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_below_minimum_threshold[500.0] PASSED [ 18%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_below_minimum_threshold[999.99] PASSED [ 20%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_above_maximum_threshold[10000000.01] PASSED [ 23%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_above_maximum_threshold[15000000.0] PASSED [ 25%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_above_maximum_threshold[100000000.0] PASSED [ 27%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_non_numeric_strings[not_a_number] PASSED [ 30%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_non_numeric_strings[] PASSED [ 32%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_non_numeric_strings[NaN_string] PASSED [ 34%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_non_numeric_strings[true] PASSED [ 37%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_non_numeric_strings[$50000] PASSED [ 39%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_nan_and_inf_payloads[NaN] PASSED [ 41%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_nan_and_inf_payloads[Infinity] PASSED [ 44%]
tests/test_m2_challenger_validation.py::TestCapitalValidationStress::test_invalid_capital_nan_and_inf_payloads[-Infinity] PASSED [ 46%]
tests/test_m2_challenger_validation.py::TestCurrencyMismatchStress::test_currency_mismatch_indian_nse_with_usd PASSED [ 48%]
tests/test_m2_challenger_validation.py::TestCurrencyMismatchStress::test_currency_mismatch_us_equities_with_inr PASSED [ 51%]
tests/test_m2_challenger_validation.py::TestCurrencyMismatchStress::test_currency_mismatch_cross_asset_payloads[CRYPTO-INR] PASSED [ 53%]
tests/test_m2_challenger_validation.py::TestCurrencyMismatchStress::test_currency_mismatch_cross_asset_payloads[COMMODITIES-INR] PASSED [ 55%]
tests/test_m2_challenger_validation.py::TestCurrencyMismatchStress::test_currency_mismatch_cross_asset_payloads[FOREX-INR] PASSED [ 58%]
tests/test_m2_challenger_validation.py::TestCurrencyMismatchStress::test_currency_mismatch_cross_asset_payloads[US_EQUITIES-EUR] PASSED [ 60%]
tests/test_m2_challenger_validation.py::TestJurisdictionMismatchStress::test_jurisdiction_mismatch_aapl_in_indian_nse PASSED [ 62%]
tests/test_m2_challenger_validation.py::TestJurisdictionMismatchStress::test_jurisdiction_mismatch_reliance_in_us_equities PASSED [ 65%]
tests/test_m2_challenger_validation.py::TestJurisdictionMismatchStress::test_jurisdiction_mismatch_cross_asset_symbols[US_EQUITIES-BTC-USD] PASSED [ 67%]
tests/test_m2_challenger_validation.py::TestJurisdictionMismatchStress::test_jurisdiction_mismatch_cross_asset_symbols[US_EQUITIES-GC=F] PASSED [ 69%]
tests/test_m2_challenger_validation.py::TestJurisdictionMismatchStress::test_jurisdiction_mismatch_cross_asset_symbols[INDIAN_NSE-EURUSD=X] PASSED [ 72%]
tests/test_m2_challenger_validation.py::TestJurisdictionMismatchStress::test_jurisdiction_mismatch_cross_asset_symbols[CRYPTO-AAPL] PASSED [ 74%]
tests/test_m2_challenger_validation.py::TestJurisdictionMismatchStress::test_jurisdiction_mismatch_cross_asset_symbols[COMMODITIES-RELIANCE.NS] PASSED [ 76%]
tests/test_m2_challenger_validation.py::TestRoutePrecedenceCollisionStress::test_route_precedence_physical_status_endpoint PASSED [ 79%]
tests/test_m2_challenger_validation.py::TestRoutePrecedenceCollisionStress::test_route_precedence_active_endpoint PASSED [ 81%]
tests/test_m2_challenger_validation.py::TestRoutePrecedenceCollisionStress::test_route_precedence_recommendations_endpoint PASSED [ 83%]
tests/test_m2_challenger_validation.py::TestRoutePrecedenceCollisionStress::test_route_precedence_reserved_subpaths_collision_guards[status] PASSED [ 86%]
tests/test_m2_challenger_validation.py::TestRoutePrecedenceCollisionStress::test_route_precedence_reserved_subpaths_collision_guards[active] PASSED [ 88%]
tests/test_m2_challenger_validation.py::TestRoutePrecedenceCollisionStress::test_route_precedence_reserved_subpaths_collision_guards[recommendations] PASSED [ 90%]
tests/test_m2_challenger_validation.py::TestBasketConfinementStress::test_basket_confinement_tampered_armed_tickers_rejected PASSED [ 93%]
tests/test_m2_challenger_validation.py::TestBasketConfinementStress::test_basket_confinement_unapproved_instrument_zero_trades PASSED [ 95%]
tests/test_m2_challenger_validation.py::TestCapitalHeadroomStress::test_capital_headroom_enforcement_prevents_overallocation PASSED [ 97%]
tests/test_m2_challenger_validation.py::TestCapitalHeadroomStress::test_capital_headroom_exhaustion_forces_cash_fallback PASSED [100%]

====================== 43 passed, 64 warnings in 11.38s =======================
```

---

## 2. Logic Chain

### 1. Capital Validation Stress (`TestCapitalValidationStress`, 20 tests)
- **Observations**:
  - `POST /api/sessions` with `allocated_capital <= 0` (-1.0, -500.0, -10000.0, 0.0, -0.0001) returns 422 Unprocessable Entity via `server.py` line 819:
    ```python
    if v <= 0:
        raise ValueError("Allocated virtual capital must be strictly positive.")
    ```
  - Sub-minimum capital (`0.01`, `100.0`, `500.0`, `999.99`) and above-maximum capital (`10,000,000.01`, `15,000,000.0`, `100,000,000.0`) are rejected via `server.py` line 821:
    ```python
    if v < 1_000.0 or v > 10_000_000.0:
        raise ValueError(f"Allocated virtual capital ({v:,.2f}) must be between 1,000 and 10,000,000.")
    ```
  - Non-numeric strings (`"not_a_number"`, `""`, `"$50000"`, `"true"`) trigger Pydantic float parsing errors (422).
  - Special floats (`"NaN"`, `"Infinity"`, `"-Infinity"`) are rejected either during Pydantic validation (422) or by `SessionManager.validate_session_parameters()` (400).
  - Direct calls to `SessionManager.validate_session_parameters()` independently enforce `min_cap = 1000.0` and `max_cap = 10_000_000.0`, rejecting all malformed/out-of-bound values with `ValueError`.

### 2. Currency Mismatch Stress (`TestCurrencyMismatchStress`, 6 tests)
- **Observations**:
  - `INDIAN_NSE` paired with `USD` returns 422 with message: `"Currency mismatch: Market 'INDIAN_NSE' requires currency 'INR', but got 'USD'."` (`server.py` line 829).
  - `US_EQUITIES` paired with `INR` returns 422 with message: `"Currency mismatch: Market 'US_EQUITIES' requires currency 'USD', but got 'INR'."`.
  - Non-NSE markets (`CRYPTO`, `COMMODITIES`, `FOREX`) paired with `INR` or `EUR` are uniformly rejected.
  - Direct backend calls to `SessionManager.validate_session_parameters()` verify identical enforcement independently of FastAPI schemas.

### 3. Jurisdiction Mismatch Stress (`TestJurisdictionMismatchStress`, 7 tests)
- **Observations**:
  - Submitting `AAPL` for `INDIAN_NSE` returns 400 with detail: `"Instrument mismatch: Ticker 'AAPL' belongs to US_EQUITIES, not the selected market 'INDIAN_NSE'."` (`server.py` line 905).
  - Submitting `RELIANCE.NS` for `US_EQUITIES` returns 400 with detail: `"Instrument mismatch: Ticker 'RELIANCE.NS' belongs to INDIAN_NSE, not the selected market 'US_EQUITIES'."`.
  - Cross-asset intrusions (`BTC-USD` in `US_EQUITIES`, `GC=F` in `US_EQUITIES`, `EURUSD=X` in `INDIAN_NSE`) are rejected via `validate_instruments_jurisdiction()` and `MarketCalendarManager.detect_market_type()`.

### 4. Route Precedence & Shadowing Guards (`TestRoutePrecedenceCollisionStress`, 6 tests)
- **Observations**:
  - `GET /api/sessions/status` resolves to `get_sessions_status()` returning physical exchange session data without colliding with `GET /api/sessions/{session_id}`.
  - `GET /api/sessions/active` resolves to `get_active_trading_session()` returning active session telemetry.
  - `POST /api/sessions/recommendations` resolves to `get_session_recommendations()` running `UniverseSelector`.
  - Malicious path traversal attempts using reserved subpaths against parameterized routes (`PUT /api/sessions/status`, `POST /api/sessions/active/start`, `POST /api/sessions/recommendations/stop`, `GET /api/sessions/status/performance`) are intercepted by `_guard_session_id()` (`server.py` line 865) returning 400 Bad Request:
    ```
    {"detail": "'status' is a reserved session route, not a valid session ID."}
    ```

### 5. Bot Execution Basket Confinement (`TestBasketConfinementStress`, 2 tests)
- **Observations**:
  - When a session is active for `["AAPL"]`, `LiveBotController.step_tick()` binds `approved_basket = set(active_session.instruments)` (`live_bot.py` line 894).
  - When `bot.armed_tickers` or `bot.watchlist` is forcefully tampered with by injecting unapproved instruments (`NVDA`, `MSFT`, `TSLA`, `BTC-USD`, `RELIANCE.NS`), `step_tick()` candidate filtering strictly enforces:
    ```python
    if tk not in approved_basket:
        continue
    ```
  - Across multiple ticks, exactly 0 positions and 0 orders were opened for any ticker outside `["AAPL"]`.

### 6. Capital Headroom Constraints (`TestCapitalHeadroomStress`, 2 tests)
- **Observations**:
  - For a session with `allocated_capital = 5,000.0 USD` on an account with $100,000 cash, `LiveBotController.step_tick()` computes headroom dynamically:
    ```python
    current_invested = sum(p.allocated_capital for p in still_open)
    remaining_session_cap = max(0.0, session_cap - current_invested - reserved_holds)
    deployable_capital = min(available_cash, remaining_session_cap)
    ```
  - When $4,950 is occupied by an existing position, remaining headroom is $50, which is below `min_trade_notional` ($100). The bot generates 0 new orders and preserves total allocation at $4,950 <= $5,000.
  - When $3,000 is 100% occupied (0 remaining headroom), the bot halts new orders and falls back to cash. Total invested capital across all positions never exceeds `allocated_capital`.

---

## 3. Caveats

1. **Shared Database State in Integration Test Runs**:
   - `server.py` defaults to `data/ledger.db`. If a separate test suite leaves an active session in `RUNNING` state, subsequent runs of `test_full_rest_session_lifecycle` in `test_trading_session_lifecycle.py` will encounter 409 Conflict until the session is stopped.
   - All tests in `tests/test_m2_challenger_validation.py` are isolated: parameter validation tests use invalid payloads that do not persist, and bot execution/headroom tests use isolated `tmp_path` SQLite databases.
2. **Review-Only Constraint Respected**:
   - In accordance with challenger guidelines, no modifications were made to implementation code in `server.py` or `src/execution/live_bot.py`.

---

## 4. Conclusion

The Milestone 2 backend parameter validation, route precedence disambiguation, bot basket confinement, and capital headroom constraints are empirically sound, robust against adversarial payloads, and fully compliant with `ORIGINAL_REQUEST.md`.

Verdict: **`APPROVE`**

---

## 5. Verification Method

To independently verify all findings and execute the empirical challenge suite:

```powershell
cd C:\Users\Shivam\Desktop\trade_bot
py -m pytest tests/test_m2_challenger_validation.py -v
```

Expected result: `43 passed` in ~11-13 seconds.
Invalidation condition: Any test failure, unhandled 500 error on invalid inputs, route shadowing on `/api/sessions/status`, or position execution outside the approved session basket.
