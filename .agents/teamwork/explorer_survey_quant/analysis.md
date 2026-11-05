# Quantitative Strategy & Modeling Investigation Report (R4 & R5)

**Platform**: SYNAPSE-TITAN Algorithmic Paper-Trading Engine  
**Author**: Quantitative Strategy Explorer (`teamwork_explorer`)  
**Date**: November 5, 2026  
**Status**: Completed Investigation  
**Working Directory**: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\explorer_survey_quant`  

---

## 1. Executive Summary

This investigation explores the quantitative, modeling, feature engineering, and execution architecture of the SYNAPSE-TITAN platform in `C:\Users\Shivam\Desktop\trade_bot`. The purpose is to provide an exhaustive blueprint for implementing Requirements **R4 (Quantitative Stock Selection, Trade Evaluation, and Portfolio Decision Engine)** and **R5 (Strategy Horizon Mapping, Market Data Integration, and Virtual Execution Guardrails)**.

### Core Discoveries:
1. **Existing Modeling Strengths**:
   - The platform possesses institutional-grade mathematical models: Causal Forward-Filtering Hidden Markov Models (eliminating Viterbi lookahead bias), High/Low Wick Triple-Barrier Meta-Labeling with Conservative Conflict Resolution (Stop-Loss priority on dual-breaches), Supervised Pinball-Loss Causal Temporal Convolutional Networks (TCN) with non-crossing monotonic quantiles ($q_{10} \le q_{50} \le q_{90}$), and Diagonal-Preserving Marchenko-Pastur Random Matrix Theory (RMT) de-noised Hierarchical Risk Parity (HRP).
   - Real-world transaction costs are rigorously modeled in `src/execution/frictions.py` (statutory schedules for US Section 31/FINRA, Indian NSE STT/GST/Stamp Duty with delivery vs. intraday differentiation, and dynamic Almgren-Chriss square-root market impact).
2. **Current Limitations to Overcome**:
   - **No Systematic Universe Selection**: The engine currently relies on static preset lists (`DEFAULT_US_EQUITIES`, `ASSET_CATALOG`) or manual UI selection. There is no automated screening module evaluating data quality, liquidity, spread, volatility, and strategy fit for setup wizard recommendations.
   - **Naive Opportunity Sorting in Live Bot**: In `src/execution/live_bot.py` (lines 981–984), candidate opportunities are sorted solely by raw win probability deviation: `abs(p - 0.50)`. This completely ignores expected win magnitude, expected loss magnitude, statutory frictions, and uncertainty bounds.
   - **No Dedicated Strategy Subsystem**: The `src/strategy/` directory does not yet exist. Quantitative decision-making is partially conflated with execution in `src/execution/live_bot.py`.
   - **Rigid Horizon Parameters**: Model lookback periods, bar intervals, and ATR multipliers are hardcoded to daily assumptions ($N_{\text{annual}} = 252$), lacking dynamic binding to 1-hour, 1-day, and 1-week user-selected trading horizons.
   - **Absence of Explainable AI Logs**: Rejected and accepted trades produce technical log strings, but lack structured, plain-language decision explanations for user activity feeds.

---

## 2. Codebase Audit & Architectural Walkthrough

### 2.1 Models (`src/models/`)

#### 1. `meta_labeler.py` (`MetaLabelingEngine`)
- **Theory**: Implements Marcos López de Prado's two-stage meta-labeling framework (AFML, Chapters 3 & 4).
- **Stage 1 (Primary Hypothesis)**: Generates primary structural directional hypothesis using 9/21 EMA crossover, 50 EMA distance, and RSI(14) bounds:
  $$\text{Signal}_t = \begin{cases} +1 & \text{if } \text{EMA}_9 > \text{EMA}_{21} \land P_t > \text{EMA}_{50} \land \text{RSI} \in [46, 75] \\ -1 & \text{if } \text{EMA}_9 < \text{EMA}_{21} \land P_t < \text{EMA}_{50} \land \text{RSI} \in [25, 54] \\ 0 & \text{otherwise} \end{cases}$$
- **Stage 2 (Triple-Barrier Secondary Labeling)**:
  - Dynamically scales profit target and stop-loss barriers by local volatility:
    $$\text{PT} = P_0 \cdot (1 + \text{pt\_mult} \cdot \sigma_{\text{local}}), \quad \text{SL} = P_0 \cdot (1 - \text{sl\_mult} \cdot \sigma_{\text{local}})$$
  - **Conservative Conflict Resolution**: Evaluates full High/Low intrabar wicks over forward holding horizon. If both PT and SL are breached in the same bar, Stop-Loss takes priority (labeled 0).
  - Horizon purging eliminates lookahead leakage across overlapping bars.
  - Fits a gradient-boosted decision tree (`LGBMClassifier` with `RandomForestClassifier` fallback) to predict $P(\text{Target}=1 \mid \text{Features})$.
  - Calibrates empirical payoff asymmetry ratio:
    $$b = \frac{\mathbb{E}[\text{Realized Return} \mid \text{Win}]}{\mathbb{E}[|\text{Realized Return}| \mid \text{Loss}]}$$

#### 2. `regime_hmm.py` (`MarketRegimeClassifier`)
- **States**:
  - State 0: Low-Vol Trending (Optimal trend continuation drift, volatility scale = 1.0)
  - State 1: Choppy Range-Bound (Mean-reverting, volatility scale = 0.6)
  - State 2: High-Vol Crisis (Extreme tail risk, circuit breaker active, volatility scale = 0.0)
- **Causal Forward-Filtering**: Computes posterior state probabilities strictly online using $\alpha_t(j) = P(X_1, \dots, X_t, S_t = j)$, eliminating global Viterbi forward-backward lookahead bias.
- **Instantaneous Jump Overrides**: Implements Parkinson High-Low range volatility to detect intraday flash crashes immediately without waiting for rolling close-to-close std updates.

#### 3. `gpu_acceleration.py` (`TorchSequenceForecaster` & `CausalQuantileTCN`)
- **Hardware Acceleration**: Automatic GPU probing (CUDA on RTX 4060, mixed precision `fp16`/`bf16`, AVX2 CPU fallback).
- **Architecture**: 4-layer Dilated Causal Convolutional Network with residual connections and non-crossing Pinball Quantile Loss:
  $$\mathcal{L}_q(y, \hat{y}) = \max(q(y - \hat{y}), (q - 1)(y - \hat{y}))$$
  Predicts monotonic quantiles $q_{10} \le q_{50} \le q_{90}$ for forward returns over horizon $H$.
- **Ensemble Fusion**: Combines LightGBM meta-probability (65%) and Causal TCN conviction (35%):
  $$p_{\text{fused}} = 0.65 \cdot p_{\text{lgbm}} + 0.35 \cdot p_{\text{tcn}}$$
  Applies False Breakout & Bull/Bear Trap veto filters when tree and neural models conflict.

#### 4. `hrp_allocator.py` (`HierarchicalRiskParity`)
- **Theory**: Marcos López de Prado's Machine Learning for Asset Managers (Chapters 2 & 7).
- **Marchenko-Pastur RMT De-noising**: Cleans empirical correlation eigenvalues exceeding the theoretical random noise boundary:
  $$\lambda_+ = \sigma^2 \left(1 + \sqrt{\frac{N}{T}}\right)^2$$
  Replaces noise eigenvalues with their constant average while strictly preserving diagonal variances:
  $$\text{diag}(\Sigma_{\text{denoised}}) \equiv \text{diag}(\Sigma_{\text{raw}})$$
- **Clustering**: Correlation distance $D_{i,j} = \sqrt{0.5(1 - \rho_{i,j})}$ clustered via Ward's minimum-variance linkage, quasi-diagonalized, and allocated via inverse-variance recursive bisection.

#### 5. `foundation_prior.py` (`VolatilityConeForecaster`)
- Projects forward price boundaries at 10th, 50th, and 90th percentiles using annualized volatility cones and directional drift.

---

### 2.2 Features (`src/features/`)

- `fracdiff.py` (`FractionalDifferentiator`): Calibrates minimum differentiation degree $d^* \in [0.1, 0.9]$ using Augmented Dickey-Fuller (ADF) test ($p < 0.05$) to achieve stationarity while preserving maximum long-term memory. Computes analytical lookback cutoff $L^*(d, \tau)$ to eliminate infinite-memory boundary truncation bias.
- `technical.py` (`TechnicalFeaturePipeline`): Leak-free technical indicator feature matrix: returns (1d, 5d, 20d), EMA distances (9, 21, 50, 200), MACD, RSI(14), ATR % (14), Realized Volatility (21d), Bollinger Bands, and Candlestick anatomy.
- `information_bars.py`: Tick, volume, and dollar bar extraction tools for tick-level sampling.

---

### 2.3 Execution & Risk Governance (`src/execution/`)

- `guardrails.py` (`RiskGuardrailEngine`):
  - **Asymmetric Fractional Kelly**:
    $$f^* = p - \frac{1 - p}{b}, \quad w_{\text{raw}} = c \cdot f^* \cdot \frac{1}{1 + 0.15 \cdot \text{Kurtosis}}$$
  - **Volatility & CVaR Tail Dampening**: Scales exposure by $\min\left(1.0, \frac{\sigma_{\text{target}}}{\sigma_{\text{realized}}}\right)$ and daily 95% CVaR threshold.
  - **Convex Drawdown Circuit Breakers**:
    - Drawdown $< 8\%$: Full operation ($1.0\times$).
    - Drawdown $\in [8\%, 15\%]$: Quadratic convex de-leveraging:
      $$\text{Scalar} = \left(1 - \frac{\text{DD} - 0.08}{0.15 - 0.08}\right)^2$$
    - Drawdown $\ge 15\%$: Hard kill switch triggered; all capital frozen in 100% cash.
    - Hard institutional single-position leverage ceiling: 20%.
- `frictions.py` (`FrictionEvaluator`):
  - Jurisdictions: `US`, `NSE_CASH`, `CRYPTO`, `FOREX`, `COMMODITY`.
  - Distinguishes NSE intraday STT (0.025% on sell) from multi-day delivery STT (0.10% on both legs), 18% GST, and exchange fees.
  - Almgren-Chriss square-root market impact:
    $$\text{Slippage}_{\text{RT}} = 2 \cdot \left[ \text{HalfSpread} + \eta \cdot \sigma_{\text{daily}} \sqrt{\frac{Q}{\text{ADV}}} \right]$$
  - Microstructure gates: Forex 17:00 EST rollover liquidity trough veto (spread quadruples), CME Gold LULD price shock halt ($>5.5\%$), and Stop-Run liquidity sweep rejection wick gate ($>78\%$ wick rejection on $>2.6\times$ median range).
- `broker.py` (`PaperBroker` & `TradingLedgerDB`):
  - Persistent SQLite ledger (`accounts`, `positions`, `trades`, `orders`, `equity_history`).
  - Pre-market order queueing with soft cash holds (`reserved_cash`).
  - Strict `PAPER_TRADING_ONLY = True` architectural invariant; real-money brokerage submission adapters are permanently disabled.
- `market_sessions.py` (`MarketCalendarManager`):
  - Real physical exchange schedules: NSE Mumbai (09:15–15:30 IST), NYSE/NASDAQ (09:30–16:00 ET with DST), CME COMEX Gold, 24/7 Crypto, 24/5 Forex.
  - Official statutory holiday calendars for 2026/2027.
- `live_bot.py` (`LiveBotController`):
  - Orchestrates the 10-step autonomous paper-trading loop.
  - Contains searchable directory `SEARCHABLE_INSTRUMENTS` (120+ assets).
  - Handles genuine market data feeds, quote freshness, and tick freezing when markets close.

---

### 2.4 Test Suite Audit
- 131 tests collected across `tests/`.
- 130 tests pass cleanly, verifying causal HMM future-invariance, FracDiff lookback, triple-barrier conflict resolution, HRP diagonal preservation, statutory friction schedules, and 20% Kelly caps.
- 1 test failure was identified in `test_gate2_adversarial_order_and_session.py`: a floating-point rounding difference of $0.010000000001$ in pytest's `approx(..., abs=0.01)` on soft cash holds.

---

## 3. Requirement R4: Systematic Universe and Opportunity Selection Engine

To satisfy R4, we design a dedicated package `src/strategy/` containing 5 modular, testable components.

```
src/strategy/
├── __init__.py
├── universe_selector.py     # Data quality, liquidity, spread & volatility filtering
├── trade_evaluator.py       # Mathematical Net Expectancy with uncertainty & frictions
├── trade_ranker.py          # Risk-adjusted ranking & regime alignment
├── portfolio_selector.py    # Kelly/HRP allocation with 100% Cash fallback
├── decision_explainer.py    # Plain-language accepted/rejected trade explanations
└── horizon_mapper.py        # Dynamic parameter binding to 1h, 1d, 1wk horizons
```

### 3.1 Module A: `UniverseSelector` (`src/strategy/universe_selector.py`)

#### Problem:
The setup wizard needs an "Auto-select for me" feature that recommends a bounded basket of instruments based on objective quantitative criteria rather than arbitrary static lists.

#### Architecture & Class Design:
```python
@dataclass
class UniverseSelectionCriteria:
    min_history_bars: int = 50
    max_missing_data_pct: float = 2.0
    min_adv_notional: float = 5_000_000.0  # Market-calibrated (USD 5M or INR 50M)
    max_spread_bps: float = 25.0
    min_annual_vol: float = 0.08
    max_annual_vol: float = 1.00
    target_basket_size: int = 5

@dataclass
class CandidateEvaluation:
    ticker: str
    market: str
    currency: str
    current_price: float
    adv_dollar_volume: float
    spread_bps: float
    annualized_vol: float
    data_quality_score: float  # [0.0, 1.0]
    passed_all_filters: bool
    rejection_reasons: List[str]
    composite_score: float
    rationale: str

@dataclass
class UniverseSelectionResult:
    market: str
    selected_instruments: List[str]
    evaluations: Dict[str, CandidateEvaluation]
    summary_rationale: str
```

#### Filtering & Scoring Logic:
1. **Data Quality Score ($Q_{\text{data}}$)**:
   $$Q_{\text{data}} = 1.0 - \left(0.5 \cdot \frac{N_{\text{missing}}}{N_{\text{expected}}} + 0.3 \cdot \frac{N_{\text{zero\_vol}}}{N_{\text{bars}}} + 0.2 \cdot \mathbb{I}(\text{Length} < N_{\text{min}})\right)$$
   Reject if $Q_{\text{data}} < 0.90$.
2. **Liquidity Gate**:
   $$\text{ADV}_{\text{notional}} = \frac{1}{20}\sum_{t=1}^{20} (\text{Close}_t \times \text{Volume}_t) \ge \text{ADV}_{\text{threshold}}$$
   - US Equities: $\ge \$5,000,000$
   - Indian NSE: $\ge \text{₹}50,000,000$
   - Crypto: $\ge \$10,000,000$
   - Forex / Commodities: Automatic pass for primary contracts
3. **Spread Gate**:
   $$\text{Spread}_{\text{bps}} = \frac{\text{Ask} - \text{Bid}}{\text{Mid}} \times 10,000 \le \text{Spread}_{\text{max}}$$
4. **Volatility Tradability Window**:
   $$\sigma_{\text{ann}} = \text{std}(\text{LogReturn}) \times \sqrt{N_{\text{annual}}} \in [\sigma_{\text{min}}, \sigma_{\text{max}}]$$
5. **Composite Selection Score**:
   $$S = 0.35 \cdot \text{Normalized}(\log(\text{ADV})) + 0.30 \cdot \text{Normalized}\left(\frac{1}{\text{Spread}_{\text{bps}}}\right) + 0.20 \cdot \text{VolScore} + 0.15 \cdot Q_{\text{data}}$$
   Select the top $K$ candidates (bounded basket, e.g. 3 to 6).

---

### 3.2 Module B: `TradeEvaluator` (`src/strategy/trade_evaluator.py`)

#### Problem:
Current trading sorts trades naively by win probability. In real trading, a trade with $P(\text{Win})=65\%$ that risks $3\%$ to make $1\%$ with $0.4\%$ friction has negative mathematical expectation!

#### Mathematical Formulation:
$$\text{Net Expectancy } (\text{EV}) = P(\text{Win}) \cdot \mathbb{E}[\text{Win} \mid \text{Win}] - P(\text{Loss}) \cdot \mathbb{E}[\text{Loss} \mid \text{Loss}] - \text{Expected Friction Cost}$$

1. **Calibrated Win Probability with Uncertainty Bounds**:
   - Fused probability from meta-model and TCN:
     $$p = 0.65 \cdot p_{\text{lgbm}} + 0.35 \cdot p_{\text{tcn}}$$
   - Epistemic uncertainty margin:
     $$\sigma_p = \sqrt{\frac{p(1 - p)}{\min(N_{\text{bars}}, 250)}} \cdot \left(1.0 + 0.2 \cdot \frac{q_{90} - q_{10}}{\max(|q_{50}|, 1e-4)}\right)$$
   - Conservative Lower-Bound Win Probability:
     $$p_{\text{conservative}} = \max(0.0, p - 1.0 \cdot \sigma_p)$$
     $$P(\text{Win}) = p_{\text{conservative}}, \quad P(\text{Loss}) = 1.0 - P(\text{Win})$$
2. **Conditional Expected Returns**:
   - For LONG:
     $$\mathbb{E}[\text{Win} \mid \text{Win}] = \frac{P_{\text{target}} - P_{\text{entry}}}{P_{\text{entry}}}$$
     $$\mathbb{E}[\text{Loss} \mid \text{Loss}] = \frac{P_{\text{entry}} - P_{\text{stop}}}{P_{\text{entry}}} + \text{Gap Risk}$$
   - For SHORT:
     $$\mathbb{E}[\text{Win} \mid \text{Win}] = \frac{P_{\text{entry}} - P_{\text{target}}}{P_{\text{entry}}}$$
     $$\mathbb{E}[\text{Loss} \mid \text{Loss}] = \frac{P_{\text{stop}} - P_{\text{entry}}}{P_{\text{entry}}} + \text{Gap Risk}$$
   - Gap Risk accounts for overnight gaps and fast-market stop execution:
     $$\text{Gap Risk} = 0.10 \times \sigma_{\text{bar}}$$
3. **Statutory & Slippage Friction Cost**:
   $$\text{Friction Cost} = \frac{\text{FrictionEvaluator.calculate\_round\_trip\_friction\_bps}(...)}{10,000}$$
4. **Net Expectancy ($\text{EV}$)**:
   $$\text{EV} = P(\text{Win}) \cdot \mathbb{E}[\text{Win} \mid \text{Win}] - (1 - P(\text{Win})) \cdot \mathbb{E}[\text{Loss} \mid \text{Loss}] - \text{Friction Cost}$$
5. **Acceptance Threshold**:
   - A trade is eligible ONLY if $\text{EV} \ge \text{min\_hurdle}$ (default $+0.20\%$) AND $P(\text{Win}) \ge 0.52$.
   - If $\text{EV} \le 0$, the trade is mathematically unsound and rejected.

---

### 3.3 Module C: `TradeRanker` (`src/strategy/trade_ranker.py`)

#### Problem:
When multiple opportunities present positive net expectancy, the platform must prioritize capital allocation to the highest risk-adjusted, regime-aligned candidates.

#### Ranking Algorithm:
1. **Risk-Adjusted Expectancy**:
   $$\text{Sharpe-Equivalent Metric} = \frac{\text{Net Expectancy}}{\sigma_{\text{asset}}}$$
2. **Market Regime Alignment Factor ($M_{\text{regime}}$)**:
   - State 0 (Low-Vol Trending):
     - Trend-congruent signals (Long in Bull Trend, Short in Bear Trend): $M = 1.25$
     - Counter-trend setups: $M = 0.70$
   - State 1 (Choppy Range-Bound):
     - Mean-reversion signals: $M = 1.15$
     - Breakout setups: $M = 0.75$
   - State 2 (High-Vol Crisis):
     - Hard Veto: $M = 0.0$ (Score forced to 0, immediate circuit breaker)
3. **Model Synergy Boost**:
   - When Causal TCN and Meta-Labeler strongly agree: $1.15\times$ boost.
4. **Final Composite Rank Score**:
   $$\text{Rank Score} = \frac{\text{EV}}{\sigma_{\text{asset}}} \times M_{\text{regime}} \times \text{SynergyBoost}$$
   Opportunities are sorted descending; any opportunity with $\text{EV} \le 0$ or $M_{\text{regime}} = 0$ is classified as `INELIGIBLE`.

---

### 3.4 Module D: `PortfolioSelector` (`src/strategy/portfolio_selector.py`)

#### Problem:
Capital must be safely allocated via Fractional Kelly or HRP, with an absolute guarantee that the portfolio allocates to **100% Cash** when no opportunities have positive expectancy.

#### Capital Allocation Modes:

#### 1. Fractional Kelly Mode:
- For each eligible opportunity $i$ with $\text{EV}_i > 0$:
  $$b_i = \frac{\mathbb{E}[\text{Win}_i \mid \text{Win}_i]}{\mathbb{E}[\text{Loss}_i \mid \text{Loss}_i]}$$
  $$f_i^* = P(\text{Win}_i) - \frac{1 - P(\text{Win}_i)}{b_i}$$
  $$w_{\text{raw}, i} = c_{\text{kelly}} \cdot f_i^* \cdot \min\left(1.0, \frac{\sigma_{\text{target}}}{\sigma_i}\right)$$
- Enforce Drawdown Dampening and Single-Position Cap ($\le 20\%$):
  $$w_i = \min(w_{\text{raw}, i} \cdot \text{DrawdownScalar}, 0.20)$$
- Leverage Normalization:
  $$\text{If } \sum_i w_i > \text{MaxGrossLeverage}: \quad w_i \leftarrow w_i \times \frac{\text{MaxGrossLeverage}}{\sum_j w_j}$$
- Residual Cash Allocation:
  $$w_{\text{cash}} = \max\left(0.0, 1.0 - \sum_i w_i\right)$$

#### 2. Hierarchical Risk Parity (HRP) Mode:
- Take the subset of assets that passed the $\text{EV} > 0$ filter.
- If subset is empty $\rightarrow$ 100% Cash.
- If subset has 1 asset $\rightarrow$ Fractional Kelly sizing, balance in Cash.
- If subset has $\ge 2$ assets:
  - Compute clean covariance via Marchenko-Pastur RMT de-noising.
  - Compute Ward's linkage HRP weights $w_{\text{hrp}, i}$.
  - Scale total gross portfolio weight by aggregate net expectancy and target volatility:
    $$W_{\text{gross}} = \min\left(1.0, \frac{\sigma_{\text{target}}}{\sigma_{\text{hrp\_port}}}, \frac{\sum_i \text{EV}_i}{\text{Hurdle}}\right)$$
    $$w_i = w_{\text{hrp}, i} \times W_{\text{gross}}, \quad w_{\text{cash}} = 1.0 - \sum_i w_i$$

#### 3. 100% Cash Allocation Guarantee:
```python
if not eligible_opportunities:
    return PortfolioAllocation(
        weights={"CASH": 1.0},
        cash_weight=1.0,
        allocated_capital_by_ticker={},
        status_message="100% CASH PRESERVED: Zero opportunities meet positive EV hurdle."
    )
```

---

### 3.5 Module E: `DecisionExplainer` (`src/strategy/decision_explainer.py`)

#### Problem:
Users need plain-language transparency in the dashboard activity feed explaining exactly why each trade was accepted or rejected.

#### Output Structure:
```python
@dataclass
class DecisionExplanation:
    ticker: str
    action: str  # "ACCEPTED", "REJECTED", "HELD_IN_CASH"
    direction: str  # "LONG", "SHORT", "NEUTRAL"
    headline: str
    plain_language_summary: str
    breakdown_factors: Dict[str, str]  # Expectancy, Regime, Frictions, Risk, Microstructure
    metrics: Dict[str, float]
    timestamp_utc: str
```

#### Example Output Feeds:
- **Accepted Trade**:
  > **ACCEPTED: LONG NVDA (Allocated: $14,500 | 14.5% equity)**  
  > *Summary*: Strong momentum breakout backed by 63.5% calibrated win probability and +1.85% net expectancy after deducting 0.18% statutory fees and L2 slippage.  
  > *Market Regime*: Low-Vol Trending (State 0) favors trend continuation.  
  > *Risk Governance*: Quarter-Kelly sizing capped at 14.5% to maintain 15% portfolio annualized volatility.
- **Rejected Trade (Negative EV)**:
  > **REJECTED: INFY.NS (Zero Allocation)**  
  > *Summary*: Trade vetoed due to negative net expectancy (-0.35%). Win probability (49.2%) is insufficient to overcome 0.32% round-trip NSE transaction taxes and statutory STT.
- **Rejected Trade (Microstructure Veto)**:
  > **REJECTED: GC=F (Zero Allocation)**  
  > *Summary*: Microstructure circuit breaker active. An extreme stop-run liquidity sweep was detected (82% wick rejection), indicating high probability of an intraday bull trap.
- **100% Cash Preservation**:
  > **PORTFOLIO ACTION: 100% CAPITAL PRESERVED IN CASH**  
  > *Summary*: All 5 scanned universe instruments failed positive net expectancy hurdles. The engine has automatically preserved 100% of virtual capital ($100,000) in cash to protect against negative-drift market conditions.

---

## 4. Requirement R5: Strategy Horizon Mapping & Virtual Execution Guardrails

### 4.1 Strategy Horizon Parameter Binding Matrix

Trading horizon (1 hour, 1 day, 1 week) dynamically governs the analytical intervals, feature windows, model horizons, and barrier thresholds:

| Parameter / Module | 1 Hour Horizon (Scalp / Intraday) | 1 Day Horizon (Day Trade / Swing) | 1 Week Horizon (Multi-Day Positional) |
| :--- | :--- | :--- | :--- |
| **Market Data Bar Interval** | `5m` (or `15m`) | `1h` (or `15m`) | `1d` (Daily) |
| **Historical Lookback Period** | `5d` (500–1000 bars) | `60d` (350–500 bars) | `2y` (504 daily bars) |
| **Fast / Slow EMA Spans** | Fast: 9, Slow: 21 (intraday bars) | Fast: 9, Slow: 21 (hourly bars) | Fast: 20, Slow: 50 (daily bars) |
| **ATR Volatility Window** | 10 bars (50 minutes) | 14 bars (14 hours / 2 days) | 14 bars (14 trading days) |
| **Annualization Factor** | $\sqrt{252 \times 6.5 \times 12} \approx 140.2$ | $\sqrt{252 \times 6.5} \approx 40.5$ | $\sqrt{252} \approx 15.87$ |
| **HMM Regime Window** | 20 bars fast Parkinson range | 21 bars composite range + return | 21 days rolling close + Parkinson |
| **TCN Sequence Length** | 30 bars (2.5 hours) | 30 bars (30 hours / ~5 days) | 30 bars (6 weeks) |
| **TCN Forecast Horizon** | 6 bars (30 minutes) | 6 bars (1 full trading day) | 5 bars (1 trading week) |
| **Profit Target ($\text{PT}$)** | $1.0 \times \text{ATR}$ | $1.5 \times \text{ATR}$ | $2.0 \times \text{ATR}$ |
| **Stop Loss ($\text{SL}$)** | $0.75 \times \text{ATR}$ | $1.0 \times \text{ATR}$ | $1.25 \times \text{ATR}$ |
| **Max Holding Period** | 12 bars (1 hour) | 7 bars (1 day) | 5 bars (1 week) |
| **Friction Schedule** | Intraday (e.g. NSE 0.025% sell STT) | Intraday / Over-night | Multi-day Delivery (NSE 0.10% buy & sell STT) |
| **Default Session-End Policy** | `CLOSE_POSITIONS` (avoid overnight risk) | `CLOSE_POSITIONS` or `KEEP_OPEN` | `KEEP_OPEN` (maintain positional trade) |

#### Implementation in `src/strategy/horizon_mapper.py`:
```python
class HorizonMapper:
    @staticmethod
    def get_horizon_config(horizon: str, market_type: str = "US") -> HorizonParameters:
        # Dynamically returns mapped parameters tailored to jurisdiction and horizon
```

---

### 4.2 Dynamic Capital Scaling Invariant

- **Decoupled Predictions**:
  $$\text{Predict}(\text{MarketData}) \rightarrow \{P(\text{Win}), \text{EV}, \text{Signal}, \text{Barriers}, d^*, \text{Regime}\}$$
  Prediction outputs are strictly invariant to account balance. Changing capital from $10,000 to $100,000 does NOT alter directional hypothesis or win probabilities.
- **Linear Dollar & Share Scaling**:
  $$\text{Allocated Dollars}_i = \text{Total Virtual Equity} \times w_i$$
  $$\text{Shares}_i = \frac{\text{Allocated Dollars}_i}{P_{\text{entry}, i}}$$
- **Buying Power Check**:
  Ensures $\sum \text{Allocated Dollars} \le \text{Available Virtual Cash}$.
- **Currency Mapping**:
  - `INDIAN_NSE`: INR (₹)
  - `US_EQUITIES`, `CRYPTO`, `COMMODITY`, `FOREX`: USD ($)

---

### 4.3 Market Data Safety & Strict Virtual Isolation

1. **Stale Data Detection & Halt**:
   - Check `quote.is_stale`, quote age $> 60\text{s}$ during open market, or quote status in `("ERROR", "MISSING", "STALE")`.
   - When a feed is stale or unavailable: **HALT new entries immediately** for that ticker.
   - **No Synthetic Price Fabrication**: Do not generate random numbers or artificial prices when live feed drops. Keep price frozen, log risk alert, and refuse execution.
2. **Strict Paper Trading Isolation**:
   - `PAPER_TRADING_ONLY = True` constant enforced at module import and in order submission.
   - All state persists exclusively to virtual SQLite database `TradingLedgerDB`.
   - External broker execution adapters (`ZerodhaKiteAdapter`, `AlpacaBrokerAdapter`, `MT5BrokerAdapter`) raise `PermissionError` if real-money execution is attempted.

---

## 5. Verification & Testing Plan

### 5.1 New Automated Unit Tests to Implement:
1. `tests/test_strategy_universe_selector.py`:
   - Test data quality rejection on corrupted/short series.
   - Test liquidity threshold filtering across US vs. NSE equities.
   - Test spread and volatility filtering.
   - Test auto-selection bounded basket output and rationale generation.
2. `tests/test_strategy_trade_evaluator.py`:
   - Test Net Expectancy formula with exact mathematical verification.
   - Test negative EV trade rejection (e.g. high friction, low win rate).
   - Test uncertainty bounds haircut on small sample sizes or wide TCN quantiles.
3. `tests/test_strategy_trade_ranker.py`:
   - Test ranking order by risk-adjusted EV.
   - Test regime alignment multipliers (boost in Trend, veto in Crisis).
4. `tests/test_strategy_portfolio_selector.py`:
   - **Critical Edge Case**: Test 100% cash allocation when all candidate trades have negative EV or are in Crisis regime.
   - Test Fractional Kelly sizing and single-position leverage cap (20%).
   - Test HRP portfolio weights on multi-asset positive EV subset.
   - Test capital scaling: verifying that doubling capital doubles shares without changing prediction probabilities.
5. `tests/test_strategy_decision_explainer.py`:
   - Test clear, plain-language text generation for accepted, rejected, and 100% cash scenarios.
6. `tests/test_strategy_horizon_mapper.py`:
   - Test parameter mapping across "1h", "1d", and "1wk".
   - Test annualization factor consistency.

### 5.2 Verification Commands:
- Existing tests: `py -m pytest tests/test_phase1_phase2_fixes.py`
- All tests: `py -m pytest tests/`
- Strategy tests: `py -m pytest tests/test_strategy_*.py`
