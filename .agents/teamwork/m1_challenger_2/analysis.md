# Empirical Challenge Report: Milestone 1 Universe Selection, Horizon Mapping & Decision Explainability

**Author**: Empirical Strategy Challenger 2 (`teamwork_challenger`, m1_challenger_2)  
**Target Repository**: `C:\Users\Shivam\Desktop\trade_bot`  
**Target Modules**: `src/strategy/universe_selector.py`, `src/strategy/horizon_mapper.py`, `src/strategy/decision_explainer.py`  
**Date**: November 5, 2026  
**Execution Environment**: Windows PowerShell, Python 3.13.7, pytest-9.2.0  

---

## 1. Executive Summary & Risk Assessment

**Overall Risk Assessment: LOW**

The modules under review (`UniverseSelector`, `HorizonMapper`, and `DecisionExplainer`) were subjected to comprehensive adversarial stress testing across corrupted data inputs, boundary conditions, mathematical invariants, and zero-division edge cases. 

A dedicated empirical challenge test suite (`tests/test_strategy_empirical_challenge.py`, 29 automated test cases) was authored and executed. All 29 adversarial tests passed. Combined with existing strategy tests and peer challenger tests, a total of **88 strategy test cases** pass with 100% success rate, 8/8 Phase 1-3 baseline mathematical invariants remain intact, and 57/57 regression tests pass without breakage.

---

## 2. Empirical Challenge Matrix & Results

### Dimension 1: `UniverseSelector` Adversarial Stress Testing

| Test ID | Stress Scenario / Input Vector | Expected Behavior | Observed Behavior | Status |
|---|---|---|---|---|
| `US-1.1` | **All-NaN OHLCV Data**: 30 bars of NaNs across Open, High, Low, Close, Volume | $Q_{\text{data}} = 0.0$, $R_{\text{missing}}=1.0$, $R_{\text{zero}}=1.0$, rejected under `LOW_DATA_QUALITY`, $S_{\text{composite}} = 0.0$ | Exact match. Rejection reason and zero composite score generated without exception. | **PASS** |
| `US-1.2` | **Negative & Zero Prices**: 25% of bars with negative close or zero low | Penalized under `missing_mask |= (df[c] <= 0)`, $Q_{\text{data}} < 0.90$, rejected under `LOW_DATA_QUALITY` | Log returns on negative transitions safely yield NaNs and are filtered via `dropna()`. Gate 1 rejects cleanly. | **PASS** |
| `US-1.3` | **Inverted High-Low**: 5 bars where High < Low | Flagged in `missing_mask`, $Q_{\text{data}} < 1.0$ | Inverted bars penalized in data quality score. | **PASS** |
| `US-1.4` | **Zero Volume (Equities)**: 30 bars of zero volume in US Equities | $R_{\text{zero}}=1.0$, $Q_{\text{data}} = 0.60 < 0.90$, rejected for `LOW_DATA_QUALITY` and `INSUFFICIENT_LIQUIDITY`, ADV = 0 | Rejected under both gates; zero ADV recorded. | **PASS** |
| `US-1.5` | **Zero Volume (Forex)**: 30 bars of zero volume in FOREX | Volume penalty bypassed ($R_{\text{zero}}=0.0$), $Q_{\text{data}}=1.0$ if prices valid | Forex exemption correctly applied; volume penalty skipped. | **PASS** |
| `US-1.6` | **Insufficient Bars (<20 bars)**: 10 bars provided | Proportional penalty $10/20 = 0.50$, rejected under `LOW_DATA_QUALITY` | Penalty formula executed correctly; candidate rejected. | **PASS** |
| `US-1.7` | **Missing Columns in OHLCV**: Missing "Volume" or "Close" column | Handled gracefully without crash; defaults to 0.0 ADV and 0.0 vol | Handled safely without unhandled KeyError. | **PASS** |
| `US-1.8` | **Infinite Prices**: `-np.inf` in Low prices | Caught by `Low <= 0` condition; bar marked corrupt | Rejected under Gate 1. | **PASS** |
| `US-2.1` | **US ADV Boundary ($5.0M USD)**: $4.99M vs $5.01M | $4.99M rejected (`INSUFFICIENT_LIQUIDITY`), $5.01M passes | Exact boundary discrimination confirmed. | **PASS** |
| `US-2.2` | **NSE ADV Boundary (₹50M INR)**: ₹49.9M vs ₹50.1M | ₹49.9M rejected (`INSUFFICIENT_LIQUIDITY`), ₹50.1M passes with `₹` currency | Exact boundary discrimination confirmed; currency symbol verified. | **PASS** |
| `US-2.3` | **Crypto ADV Boundary ($10M USD)**: $9.99M vs $10.01M | $9.99M rejected, $10.01M passes | Exact boundary discrimination confirmed. | **PASS** |
| `US-2.4` | **Commodities ADV Boundary ($10M USD)**: $9.99M vs $10.01M | $9.99M rejected, $10.01M passes | Exact boundary discrimination confirmed. | **PASS** |
| `US-2.5` | **Forex ADV Boundary ($25M USD)**: $24.99M vs $25.01M | $24.99M rejected, $25.01M passes | Exact boundary discrimination confirmed. | **PASS** |
| `US-3.1` | **Spread Gate Boundary (25.0 bps)**: 24.9 bps vs 25.1 bps | 24.9 bps passes, 25.1 bps rejected (`SPREAD_TOO_WIDE`) | Strict inequality `spread > max_spread_bps` verified. | **PASS** |
| `US-4.1` | **Volatility Floor Boundary (8.0%)**: 7.9% vs 8.1% | 7.9% rejected (`STAGNANT_VOLATILITY`), 8.1% passes | Stagnant volatility threshold enforced. | **PASS** |
| `US-4.2` | **Volatility Ceiling Boundary (100.0%)**: 99.9% vs 100.1% | 99.9% passes, 100.1% rejected (`EXCESSIVE_VOLATILITY`) | Tail risk ceiling enforced. | **PASS** |
| `US-5.1` | **Basket Clamping**: target_size $\in \{-10, 0, 1, 2, 7, 10, 50, 1000\}$ | Clamped strictly to $[3, 6]$ whenever sufficient candidates pass | Basket size clamped to 3 (for $\le 3$) and 6 (for $\ge 6$). | **PASS** |
| `US-5.2` | **Sub-3 Candidates Available**: Only 2 candidates pass | Returns 2 candidates with explicit `WARNING: Only 2 instruments...` | Correct fallback rationale and basket count. | **PASS** |
| `US-5.3` | **Zero Candidates Available**: 0 candidates pass | Returns `[]` with `REJECTION: Zero candidate instruments...` | Clean empty basket and rejection summary. | **PASS** |

---

### Dimension 2: `HorizonMapper` Adversarial Stress Testing

| Test ID | Stress Scenario / Input Vector | Expected Behavior | Observed Behavior | Status |
|---|---|---|---|---|
| `HM-1.1` | **Analytical Annualization Factor 1h**: $\sqrt{252 \times 78} = 140.1998...$ | Exactly `140.2` | Matched `140.2` exactly. | **PASS** |
| `HM-1.2` | **Analytical Annualization Factor 1d**: $\sqrt{252 \times 6.5} = 40.4722...$ | Exactly `40.5` | Matched `40.5` exactly. | **PASS** |
| `HM-1.3` | **Analytical Annualization Factor 1wk**: $\sqrt{252 \times 1.0} = 15.8745...$ | Exactly `15.87` | Matched `15.87` exactly. | **PASS** |
| `HM-2.1` | **Parameter Coverage Across 19 Fields**: All 3 horizons | Complete parameter population across intervals, lookbacks, TCN seq, triple barriers, frictions, and end policies | All 19 fields uniquely and correctly bound for 1h, 1d, 1wk. | **PASS** |
| `HM-3.1` | **Horizon Aliases & Shorthand**: 22 variations ("1h", "1H", "intraday", "daily", "swing", "1wk") | All normalize to canonical `"1 hour"`, `"1 day"`, or `"1 week"` | Clean normalization across all aliases. | **PASS** |
| `HM-3.2` | **Invalid Horizon Inputs**: `"2 hours"`, `"1 month"`, `"5m"`, `"bi-weekly"`, `""`, `"   "` | Explicit `ValueError("Unsupported trading horizon...")` | Raised `ValueError` with descriptive message on every invalid string. | **PASS** |
| `HM-4.1` | **Immutability of Parameters**: Attempting to alter `HorizonParameters` fields | `dataclasses.FrozenInstanceError` raised | Immutable container prevents runtime tampering. | **PASS** |

---

### Dimension 3: `DecisionExplainer` Adversarial Stress Testing

| Test ID | Stress Scenario / Input Vector | Expected Behavior | Observed Behavior | Status |
|---|---|---|---|---|
| `DE-1.1` | **Accepted Trade (USD, LONG)**: High positive Net EV | Headline contains BUY, ticker, EV%, win prob. Summary contains friction bps, allocation %, capital, target, stop. All 6 factor keys and 12 metric keys present. | Verified complete text formatting and quantitative metric mapping. | **PASS** |
| `DE-1.2` | **Accepted Trade (INR, SHORT)**: TCS.NS short trade | Headline contains SELL, ticker. Summary displays `₹` currency symbols and capital amounts. | Verified currency switching and short action semantics. | **PASS** |
| `DE-1.3` | **Zero-Division Resilience**: entry_price = 0.0, expected_loss = 0.0 | No `ZeroDivisionError`; clamped via `max(..., 1e-4)` | Protected against division by zero; output valid. | **PASS** |
| `DE-2.1` | **Rejection (Negative Net Expectancy)**: Net EV $\le 0.0$ | Headline displays `REJECTED <ticker>: Negative Net Expectancy (<EV>%)`. Summary explains gross prob vs fee drag. | Clear, honest rationale generated. | **PASS** |
| `DE-2.2` | **Rejection (Crisis Regime Quarantine)**: Market regime State 2 | Headline displays `REJECTED <ticker>: Crisis Regime Quarantine`. Summary references State 2 risk protection. | Crisis quarantine clearly communicated. | **PASS** |
| `DE-2.3` | **Rejection (Microstructure Veto)**: Forex 17:00 EST rollover | Headline displays `REJECTED <ticker>: Microstructure Circuit Breaker`. Summary includes specific veto cause. | Microstructure explanation verified. | **PASS** |
| `DE-2.4` | **Rejection (Sub-hurdle EV)**: Net EV $+0.10\% < +0.20\%$ | Headline displays `REJECTED <ticker>: Insufficient Edge`. | Insufficient edge clearly stated. | **PASS** |
| `DE-3.1` | **100% Cash Allocation Narrative**: Zero positive EV trades | Headline: `100% CASH PRESERVED: Zero Opportunities Satisfy Edge Hurdle`. All 5 factors and 4 metrics populated. | Narrative comprehensively explains capital preservation. | **PASS** |
| `DE-4.1` | **Batch Allocation Result Translation**: Mixed portfolio (accepted + rejected) | Correctly maps `PortfolioAllocationResult` to individual candidate explanations. | All candidates receive corresponding explanations. | **PASS** |

---

## 3. Challenges & Findings

### Challenge 1: Log-Return Generation on Negative Prices in Volatility Estimator
- **Observation**: When testing corrupted OHLCV containing isolated negative closes, `np.log(closes / closes.shift(1))` generates `NaN` for non-positive transitions, triggering a `RuntimeWarning: invalid value encountered in log`.
- **Attack Scenario**: If a dirty bar enters `compute_annualized_volatility`, could it crash or produce `NaN` volatility that circumvents the $[8\%, 100\%]$ boundary checks?
- **Empirical Finding**: 
  - If alternating negative and positive closes exist throughout, `closes.dropna()` leaves zero valid transitions, producing `NaN` for volatility. In Python, `float('nan') < 0.08` and `float('nan') > 1.00` both evaluate to `False`.
  - However, Gate 1 (`evaluate_data_quality`) runs *prior* to Gate 4 and flags any bar where `Close <= 0` or `Low <= 0` in `missing_mask`. If more than 10% of bars are affected, the instrument is immediately rejected under `LOW_DATA_QUALITY`.
  - If fewer than 10% of bars are affected, `dropna()` drops the invalid transitions, and standard deviation is computed over the remaining valid transitions.
  - Furthermore, `evaluate_instrument` explicitly sets `composite_score = 0.0` unless `passed_all_gates` is `True`.
- **Verdict**: Handled safely. Recommends adding an explicit check for `np.isnan(ann_vol)` in Gate 4 during future refactoring as an extra layer of defense-in-depth.

### Challenge 2: Clamping of Non-Positive Basket Target Sizes
- **Observation**: If a frontend or API caller passes `target_size <= 0` (e.g. `0` or `-5`), how does `auto_select_basket` behave?
- **Empirical Finding**:
  - The implementation calculates `k_target = max(self.criteria.target_basket_min, min(self.criteria.target_basket_max, target_size))`.
  - For `target_size = 0` or negative values, `min(6, 0) = 0`, then `max(3, 0) = 3`.
  - The basket size is strictly clamped to `target_basket_min` (3).
- **Verdict**: Robust. Clamping behavior functions properly across all integer inputs.

---

## 4. Verification Proof

### Test Execution Summary

```powershell
Set-Location "C:\Users\Shivam\Desktop\trade_bot"

# 1. Full strategy suite including empirical challenge tests
py -m pytest (Get-Item tests/test_strategy_*.py).FullName -v
# Output: 88 passed, 2 warnings in 5.32s

# 2. Baseline Phase 1, 2 & 3 mathematical invariants
py tests/test_phase1_phase2_fixes.py
# Output: ALL 8 PHASE 1, 2 & 3 MATHEMATICAL & MICROSTRUCTURE INVARIANTS VERIFIED

# 3. Regression test suites
py -m pytest tests/test_market_sessions.py tests/test_real_market_paper_trading.py
# Output: 57 passed, 58 warnings in 9.81s
```

All verification criteria are fully satisfied.
