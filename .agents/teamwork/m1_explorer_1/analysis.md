# Quantitative Strategy Engine Analysis: UniverseSelector & HorizonMapper

**Module Focus**: Milestone 1 (Part A) — `src/strategy/universe_selector.py` & `src/strategy/horizon_mapper.py`  
**Author**: Universe and Horizon Explorer (`teamwork_explorer`)  
**Target Repository**: `C:\Users\Shivam\Desktop\trade_bot`  
**Date**: November 5, 2026  

---

## 1. Executive Summary & Architectural Context

The SYNAPSE-TITAN platform requires a robust quantitative onboarding and dynamic strategy execution layer to replace static assumptions with institutional-grade quantitative discipline. 

Prior to Milestone 1:
1. `src/strategy/` did not exist. Candidate instruments were hardcoded in `src/execution/live_bot.py` or selected via naive probability sorting ($|p - 0.50|$), completely ignoring data quality, liquidity, spread drag, and volatility tradability bounds.
2. Strategy parameters were hardcoded for daily trading: annualization factor was fixed at $\sqrt{252}$ (`src/features/technical.py:81`, `src/models/regime_hmm.py:92`), lookback period was fixed at `"2y"` or `"1y"`, intervals were fixed at `"1d"`, and stop/target multipliers were static.

Milestone 1 introduces the `src/strategy/` package. This report delivers the complete technical design, mathematical formulations, algorithmic logic, class blueprints, and test specifications for:
- **`UniverseSelector` (`src/strategy/universe_selector.py`)**: Institutional multi-gate filtering (Data Quality $\ge 0.90$, ADV Liquidity, Spread $\le 25$ bps, Volatility $8\%-100\%$), composite multi-factor scoring, and bounded basket auto-selection (3 to 6 instruments) with clear setup wizard rationales.
- **`HorizonMapper` (`src/strategy/horizon_mapper.py`)**: Dynamic binding across trading horizons (1 hour, 1 day, 1 week) mapping bar intervals, lookbacks, EMA spans, ATR windows, exact annualization factors (**140.2** for 1h, **40.5** for 1d, **15.87** for 1wk), HMM windows, TCN sequence lengths & prediction horizons, profit target and stop loss volatility multipliers, max holding bars, and session-end policies.

---

## 2. UniverseSelector: Mathematical Formulations & Class Design

### 2.1 Core Architectural Principles
The setup wizard requires an "Auto-select for me" feature where users choose a target market (US Equities, Indian Equities, Crypto, Commodities, Forex), and the engine autonomously screens, evaluates, scores, and recommends an optimal basket of 3 to 6 instruments.

To protect virtual capital and guarantee paper-trading realism, four sequential, non-compensatory **Hard Institutional Gates** are enforced:
$$\text{Candidate Passes} \iff \text{Gate}_1 \land \text{Gate}_2 \land \text{Gate}_3 \land \text{Gate}_4$$

If any gate fails, the candidate is rejected with an explicit, human-readable reason. Only passing candidates proceed to **Composite Multi-Factor Scoring**.

```
[Candidate Instruments]
         │
         ▼
┌─────────────────────────────────┐
│ Gate 1: Data Quality Score      │──[ Fail: Q_data < 0.90 ]──► REJECTED (Missing/Flat Bars)
│ Q_data >= 0.90                  │
└─────────────────────────────────┘
         │ (Pass)
         ▼
┌─────────────────────────────────┐
│ Gate 2: ADV Liquidity Gate      │──[ Fail: ADV < Threshold ]──► REJECTED (Illiquid / High Impact)
│ US >= $5M, NSE >= ₹50M, etc.    │
└─────────────────────────────────┘
         │ (Pass)
         ▼
┌─────────────────────────────────┐
│ Gate 3: Spread Gate             │──[ Fail: Spread > 25 bps ]──► REJECTED (Excessive Friction)
│ Spread <= 25 bps                │
└─────────────────────────────────┘
         │ (Pass)
         ▼
┌─────────────────────────────────┐
│ Gate 4: Volatility Bounds       │──[ Fail: Vol < 8% or > 100% ]──► REJECTED (Stagnant or Hyper-Vol)
│ 8.0% <= Vol_ann <= 100.0%       │
└─────────────────────────────────┘
         │ (Pass)
         ▼
┌────────────────────────────────────────────────────────┐
│ Composite Multi-Factor Scoring                         │
│ S_composite = 0.35 S_liq + 0.25 S_spread + 0.20 S_qual │
│             + 0.20 S_vol                               │
└────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────┐
│ Bounded Basket Auto-Selection (3 to 6 Instruments)    │
│ Ranked descending with setup wizard rationale          │
└────────────────────────────────────────────────────────┘
```

---

### 2.2 Gate 1: Data Quality Score ($Q_{\text{data}} \ge 0.90$)

#### Theoretical Justification
Financial machine learning models (Causal HMM, Fractional Differentiation, Supervised TCN) fail when time-series data contains missing bars, timestamp discontinuities, stale flat-lines, or zero-volume bars (indicating feed dropouts or suspended trading).

#### Mathematical Formulation
Given an OHLCV sample of $N_{\text{rows}}$ over the evaluation window:
1. **Missing / Invalid Bar Ratio ($R_{\text{missing}}$)**:
   A bar is classified as missing/invalid if any of `Open, High, Low, Close` is NaN, null, non-positive ($\le 0$), or if $High < Low$:
   $$N_{\text{missing}} = \sum_{t=1}^N \mathbf{1}_{\{\text{Open}_t \le 0 \lor \text{High}_t \le 0 \lor \text{Low}_t \le 0 \lor \text{Close}_t \le 0 \lor \text{High}_t < \text{Low}_t \lor \text{NaN}\}}$$
   $$R_{\text{missing}} = \frac{N_{\text{missing}}}{N_{\text{rows}}}$$

2. **Zero-Volume Bar Ratio ($R_{\text{zero\_vol}}$)**:
   For volume-bearing markets (US Equities, NSE Equities, Crypto, Commodities), bars with $\text{Volume} \le 0$ or NaN indicate illiquidity or feed stalls:
   $$N_{\text{zero\_vol}} = \sum_{t=1}^N \mathbf{1}_{\{\text{Volume}_t \le 0 \lor \text{Volume is NaN}\}}$$
   $$R_{\text{zero\_vol}} = \frac{N_{\text{zero\_vol}}}{N_{\text{rows}}}$$
   *(Note: For Forex spot feeds where tick volume is non-standard or omitted, $R_{\text{zero\_vol}}$ is weighted 0.0, evaluating data quality purely on price continuity and non-zero volatility).*

3. **Composite Data Quality Metric**:
   $$Q_{\text{data}} = \max\left(0.0, 1.0 - \left(0.60 \cdot R_{\text{missing}} + 0.40 \cdot R_{\text{zero\_vol}}\right)\right)$$
   Clamped to $[0.0, 1.0]$.
   If $N_{\text{rows}} < N_{\text{min\_required}}$ (default 20 bars), a history length penalty applies:
   $$Q_{\text{data}} = Q_{\text{data}} \cdot \frac{N_{\text{rows}}}{N_{\text{min\_required}}}$$

4. **Pass/Fail Criterion**:
   $$\text{Gate}_1 = \begin{cases} \text{PASS}, & \text{if } Q_{\text{data}} \ge 0.90 \\ \text{FAIL}, & \text{if } Q_{\text{data}} < 0.90 \end{cases}$$
   Rejection Reason: `"LOW_DATA_QUALITY: Data Quality Score {Q_data:.1%} is below the 90.0% threshold (missing bar ratio: {R_missing:.1%}, zero volume ratio: {R_zero_vol:.1%})."`

---

### 2.3 Gate 2: ADV Liquidity Gate

#### Theoretical Justification
Low-liquidity instruments incur severe market impact under Almgren-Chriss square-root laws:
$$\text{Impact}_{\text{bps}} \propto \eta \cdot \sigma_{\text{daily}} \cdot \sqrt{\frac{Q_{\text{order}}}{\text{ADV}}}$$
When ADV is low, participation rates exceed institutional ceilings (e.g. 5%), leading to severe slippage that invalidates model alpha.

#### Mathematical Formulation
1. **Daily Dollar/Currency Volume**:
   $$\text{NotionalVol}_t = \text{Close}_t \times \text{Volume}_t$$
2. **Rolling Average Daily Volume (ADV)**:
   Computed over the last $K = \min(N, 20)$ trading bars:
   $$\text{ADV} = \frac{1}{K} \sum_{i=1}^K \text{NotionalVol}_{N - K + i}$$
3. **Market-Specific Liquidity Thresholds ($\text{ADV}_{\text{thresh}}$)**:
   - **US Equities** (`US` / `US_EQUITIES`):
     $$\text{ADV} \ge \$5,000,000\text{ USD}$$
   - **Indian Equities** (`NSE_CASH` / `INDIAN_NSE`):
     $$\text{ADV} \ge \text{₹}50,000,000\text{ INR} \quad (\approx \$600,000\text{ USD equivalent})$$
   - **Cryptocurrencies** (`CRYPTO`):
     $$\text{ADV} \ge \$10,000,000\text{ USD}$$
   - **Commodities** (`COMMODITIES`):
     $$\text{ADV} \ge \$10,000,000\text{ USD}$$
   - **Forex Majors** (`FOREX`):
     $$\text{ADV} \ge \$25,000,000\text{ USD equivalent}$$
4. **Pass/Fail Criterion**:
   $$\text{Gate}_2 = \begin{cases} \text{PASS}, & \text{if } \text{ADV} \ge \text{ADV}_{\text{thresh}}(\text{market}) \\ \text{FAIL}, & \text{if } \text{ADV} < \text{ADV}_{\text{thresh}}(\text{market}) \end{cases}$$
   Rejection Reason: `"INSUFFICIENT_LIQUIDITY: ADV of {currency}{ADV:,.0f} is below the {currency}{threshold:,.0f} institutional liquidity gate."`

---

### 2.4 Gate 3: Spread Gate ($\le 25\text{ bps}$)

#### Theoretical Justification
The bid-ask spread represents immediate round-trip friction. When spread exceeds 25 basis points (0.25%), friction overwhelms high-frequency or multi-day alpha signals.

#### Mathematical Formulation
1. **Spread Evaluation Hierarchy**:
   - **Primary (Live Quote BBO)**: If a `LiveQuote` is available, valid, and has positive bid and ask:
     $$\text{Spread}_{\text{bps}} = \frac{\text{Ask} - \text{Bid}}{\text{Mid}} \times 10,000 \quad \text{where } \text{Mid} = \frac{\text{Ask} + \text{Bid}}{2}$$
   - **Secondary (Corwin-Schultz High-Low Estimator)**: If the market is closed or live quote is unavailable, evaluate the 2-day Corwin-Schultz (2012) spread from OHLC bars:
     $$\beta = \sum_{j=0}^1 \left[\ln\left(\frac{\text{High}_{t-j}}{\text{Low}_{t-j}}\right)\right]^2, \quad \gamma = \left[\ln\left(\frac{\max(\text{High}_t, \text{High}_{t-1})}{\min(\text{Low}_t, \text{Low}_{t-1})}\right)\right]^2$$
     $$\alpha = \frac{\sqrt{2\beta} - \sqrt{\beta}}{3 - 2\sqrt{2}} - \sqrt{\frac{\gamma}{3 - 2\sqrt{2}}}, \quad \text{Spread}_{\text{est}} = \frac{2(e^\alpha - 1)}{1 + e^\alpha} \times 10,000$$
   - **Fallback (Jurisdiction Baseline)**:
     $$\text{Spread}_{\text{bps}} = 2 \times \text{profile.slippage\_bps}$$
2. **Pass/Fail Criterion**:
   $$\text{Gate}_3 = \begin{cases} \text{PASS}, & \text{if } \text{Spread}_{\text{bps}} \le 25.0\text{ bps} \\ \text{FAIL}, & \text{if } \text{Spread}_{\text{bps}} > 25.0\text{ bps} \end{cases}$$
   Rejection Reason: `"SPREAD_TOO_WIDE: Bid-Ask spread of {Spread_bps:.1f} bps exceeds the 25.0 bps maximum execution gate."`

---

### 2.5 Gate 4: Volatility Tradability Bounds ($8.0\% \le \sigma_{\text{ann}} \le 100.0\%$)

#### Theoretical Justification
- **Lower Bound (8.0% Annualized)**: Instruments with volatility below 8% (e.g. ultra-short Treasury bills, pegged stablecoins, stagnant utility stocks) do not exhibit enough variance to overcome round-trip statutory frictions (exchange fees, STT, GST, broker commissions). Capital placed in them becomes "dead money."
- **Upper Bound (100.0% Annualized)**: Instruments with volatility exceeding 100% (e.g. meme tokens, distressed penny stocks, leveraged inverse decay instruments) exhibit extreme leptokurtosis and jump risk, destabilizing Kelly position sizing and causing repeated circuit-breaker halts.

#### Mathematical Formulation
1. **Sample Log Returns**:
   $$r_t = \ln\left(\frac{\text{Close}_t}{\text{Close}_{t-1}}\right)$$
2. **Annualized Volatility**:
   $$\sigma_{\text{ann}} = \text{std}(r) \times F_{\text{ann}}$$
   where $F_{\text{ann}} = \sqrt{252} \approx 15.8745$ for daily evaluation.
3. **Pass/Fail Criterion**:
   $$\text{Gate}_4 = \begin{cases} \text{PASS}, & \text{if } 0.08 \le \sigma_{\text{ann}} \le 1.00 \\ \text{FAIL (Low)}, & \text{if } \sigma_{\text{ann}} < 0.08 \\ \text{FAIL (High)}, & \text{if } \sigma_{\text{ann}} > 1.00 \end{cases}$$
   Rejection Reasons:
   - Low: `"STAGNANT_VOLATILITY: Annualized volatility of {sigma_ann:.1%} is below 8.0% minimum tradability floor. Alpha potential is insufficient to cover friction."`
   - High: `"EXCESSIVE_VOLATILITY: Annualized volatility of {sigma_ann:.1%} exceeds 100.0% maximum risk ceiling. Extreme tail risk renders position sizing unstable."`

---

### 2.6 Composite Multi-Factor Scoring Formula

For all candidates satisfying $\text{Gate}_1 \land \text{Gate}_2 \land \text{Gate}_3 \land \text{Gate}_4$, a composite ranking score $S_{\text{composite}} \in [0.0, 1.0]$ is computed:
$$S_{\text{composite}} = 0.35 \cdot S_{\text{liq}} + 0.25 \cdot S_{\text{spread}} + 0.20 \cdot S_{\text{qual}} + 0.20 \cdot S_{\text{vol}}$$

#### Component Factor Definitions:
1. **Normalized Liquidity Factor ($S_{\text{liq}}$)**:
   Logarithmic scaling between the minimum threshold and $20\times$ the threshold:
   $$S_{\text{liq}} = \min\left(1.0, \max\left(0.0, \frac{\ln(\text{ADV}) - \ln(\text{ADV}_{\text{thresh}})}{\ln(20 \cdot \text{ADV}_{\text{thresh}}) - \ln(\text{ADV}_{\text{thresh}})}\right)\right)$$
2. **Normalized Spread Tightness Factor ($S_{\text{spread}}$)**:
   Linear inversion over the $[0, 25]$ bps range:
   $$S_{\text{spread}} = \min\left(1.0, \max\left(0.0, 1.0 - \frac{\text{Spread}_{\text{bps}}}{25.0}\right)\right)$$
3. **Normalized Data Quality Factor ($S_{\text{qual}}$)**:
   Scaled over the allowable range $[0.90, 1.00]$:
   $$S_{\text{qual}} = \min\left(1.0, \max\left(0.0, \frac{Q_{\text{data}} - 0.90}{0.10}\right)\right)$$
4. **Volatility Sweet-Spot Factor ($S_{\text{vol}}$)**:
   Gaussian bell curve centered at the quantitative sweet spot of $\mu = 30\%$ annualized volatility with $\sigma = 18\%$:
   $$S_{\text{vol}} = \exp\left( - \frac{(\sigma_{\text{ann}} - 0.30)^2}{2 \cdot (0.18)^2} \right)$$
   This rewards optimal tradability ($20\%-40\%$ vol) while smoothly penalizing borderline instruments near $8\%$ or $100\%$.

---

### 2.7 Bounded Basket Auto-Selection Algorithm

The wizard setup requires recommending between **3 and 6 instruments** (default: 5):
1. **Target Clamping**:
   $$K_{\text{target}} = \min(6, \max(3, \text{target\_size}))$$
2. **Ranking**:
   Sort passing candidates in descending order of $S_{\text{composite}}$.
3. **Selection**:
   - If $N_{\text{passed}} \ge K_{\text{target}}$: select the top $K_{\text{target}}$ candidates.
   - If $3 \le N_{\text{passed}} < K_{\text{target}}$: select all $N_{\text{passed}}$ candidates.
   - If $0 < N_{\text{passed}} < 3$: select all $N_{\text{passed}}$ passing candidates, but include a prominent setup wizard warning that market conditions yielded fewer than the institutional minimum of 3 instruments.
   - If $N_{\text{passed}} == 0$: return `selected_instruments = []`, with an explicit explanation that zero candidates passed the risk gates.

#### Setup Wizard Rationale Output
The algorithm generates:
1. **Basket Summary Rationale**:
   `"Auto-selected 5 high-conviction US Equities (NVDA, AAPL, MSFT, AMZN, META) with aggregate ADV of $38.4B, average spread of 2.1 bps, and mean annualized volatility of 31.4%. All instruments passed strict data quality (>=90%) and institutional liquidity gates."`
2. **Per-Candidate Justification**:
   - For accepted: `"NVDA: Passed all gates (ADV $14.2B >> $5M, spread 1.5 bps <= 25 bps, vol 38.4% in [8%, 100%], data quality 99.8%). Top-tier liquidity and tradability."`
   - For rejected: `"XYZ: Rejected due to SPREAD_TOO_WIDE (Spread 34.2 bps > 25.0 bps gate) and INSUFFICIENT_LIQUIDITY (ADV $2.1M < $5.0M gate)."`

---

## 3. HorizonMapper: Multi-Horizon Dynamic Binding

### 3.1 Holding Horizon vs Session Run Duration Distinction

A foundational architectural requirement is differentiating **Holding Horizon** from **Session Run Duration**:

| Concept | Governed By | Scope & Impact | Examples |
|---|---|---|---|
| **Holding Horizon** | `HorizonMapper` & Strategy Engine | Dictates bar frequency, technical feature spans, prediction horizon, volatility annualization, and triple-barrier stop/target placement. | 1 hour, 1 day, 1 week |
| **Session Run Duration** | `SessionManager` & Execution Engine | Dictates the operational lifespan of the autonomous trading bot session before executing session-end position policies. | 1 hour, 4 hours, 1 day, 1 week, custom, manual stop |

*Example*: A user initiates a **4-hour session** with a **1-hour holding horizon**. The bot downloads 5-minute bars, runs 1-hour prediction cycles, opens and manages trades with 1-hour expected holding periods, and upon reaching the 4-hour mark, enforces the session-end policy (`CLOSE_POSITIONS` or `KEEP_OPEN`).

---

### 3.2 Exact Horizon Parameter Specifications

```
                     ┌────────────────────────────────────────────────────────┐
                     │                 Selected Horizon                       │
                     └────────────────────────────────────────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
   [ 1 Hour ]                 [ 1 Day ]                 [ 1 Week ]
   - 5m Bars                  - 1h Bars                 - 1d Bars
   - Lookback: 5d             - Lookback: 60d           - Lookback: 2y
   - Factor: 140.2            - Factor: 40.5            - Factor: 15.87
   - TCN Seq: 24, Horiz: 12   - TCN Seq: 30, Horiz: 7   - TCN Seq: 30, Horiz: 5
   - PT: 1.0x, SL: 0.75x      - PT: 1.5x, SL: 1.0x      - PT: 2.0x, SL: 1.25x
   - Max Hold: 12 bars        - Max Hold: 7 bars        - Max Hold: 5 bars
   - End: CLOSE_POSITIONS     - End: CLOSE_POSITIONS    - End: KEEP_OPEN
   - Intraday STT: True       - Intraday STT: True      - Delivery STT: False
```

#### Detailed Parameter Mapping Table:

| Parameter | 1 Hour (`1h`) | 1 Day (`1d`) | 1 Week (`1wk`) | Rationale / Mathematical Derivation |
|---|---|---|---|---|
| `horizon_name` | `"1 hour"` | `"1 day"` | `"1 week"` | Standard canonical name |
| `category` | `"INTRADAY"` | `"DAILY"` | `"SWING"` | Execution style categorization |
| `bar_interval` | `"5m"` | `"1h"` | `"1d"` | Optimal bar resolution |
| `secondary_interval`| `"1m"` | `"15m"` | `"1h"` | Micro-execution / entry resolution |
| `lookback_period` | `"5d"` | `"60d"` | `"2y"` | Stays within Yahoo 60d intraday limit |
| `min_bars_required` | 60 | 100 | 150 | Minimum warmup bars for indicators |
| `feature_fast_ema` | 9 | 9 | 9 | Fast momentum span |
| `feature_slow_ema` | 21 | 21 | 21 | Slow trend span |
| `feature_macro_ema`| 50 | 50 | 200 | Structural regime filter span |
| `atr_window` | 14 | 14 | 14 | Standard True Range smoothing |
| **`annualization_factor`** | **`140.2`** | **`40.5`** | **`15.87`** | $\sqrt{N_{\text{bars/yr}}}$ (exact derivations below) |
| `bars_per_day` | 78.0 | 6.5 | 1.0 | Standard 6.5-hour trading day |
| `hmm_window_bars` | 60 | 120 | 252 | Rolling causal regime estimation window |
| `tcn_seq_len` | 24 | 30 | 30 | Input sequence length (in bars) |
| `tcn_horizon_bars` | 12 | 7 | 5 | Target prediction horizon (in bars) |
| `pt_vol_mult` | 1.0 | 1.5 | 2.0 | Profit-taking barrier multiplier ($\times \sigma_{\text{bar}}$) |
| `sl_vol_mult` | 0.75 | 1.0 | 1.25 | Stop-loss barrier multiplier ($\times \sigma_{\text{bar}}$) |
| `vol_floor_bar` | 0.003 (0.3%) | 0.008 (0.8%) | 0.015 (1.5%) | Minimum single-bar volatility floor |
| `max_holding_bars` | 12 | 7 | 5 | Expiry time barrier ($\tau$) in bars |
| `is_intraday_friction`| `True` | `True` | `False` | Toggles intraday vs delivery NSE STT |
| `default_session_end_policy`| `"CLOSE_POSITIONS"`| `"CLOSE_POSITIONS"`| `"KEEP_OPEN"` | Intraday closes; swing stays open |
| `staleness_sec` | 60.0 | 300.0 | 1800.0 | Maximum allowable quote age before halting |
| `signal_cooldown_bars`| 3 | 2 | 1 | Minimum bars between entries |

---

### 3.3 Exact Derivations of Annualization Factors

The annualization factor $F_{\text{ann}}$ scales per-bar volatility $\sigma_{\text{bar}}$ to annualized volatility $\sigma_{\text{ann}}$:
$$\sigma_{\text{ann}} = \sigma_{\text{bar}} \times F_{\text{ann}} = \sigma_{\text{bar}} \times \sqrt{N_{\text{bars/year}}}$$

1. **1-Hour Horizon (5-minute bars)**:
   - Regular Trading Hours: 6.5 hours/day (09:30 to 16:00 EST) = 390 minutes.
   - Number of 5-minute bars per day: $390 / 5 = 78$ bars/day.
   - Trading days per year: 252 days.
   - Total bars per year: $N = 252 \times 78 = 19,656$ bars.
   - Annualization Factor:
     $$F_{\text{ann}} = \sqrt{19,656} = 140.1998573... \approx \mathbf{140.2}$$

2. **1-Day Horizon (1-hour bars)**:
   - Regular Trading Hours: 6.5 hours/day $\implies 6.5$ bars/day.
   - Total bars per year: $N = 252 \times 6.5 = 1,638$ bars.
   - Annualization Factor:
     $$F_{\text{ann}} = \sqrt{1,638} = 40.4722127... \approx \mathbf{40.5}$$

3. **1-Week Horizon (Daily 1d bars)**:
   - Regular Trading Hours: 1 bar/day.
   - Total bars per year: $N = 252 \times 1 = 252$ bars.
   - Annualization Factor:
     $$F_{\text{ann}} = \sqrt{252} = 15.8745078... \approx \mathbf{15.87}$$

These numbers are mathematically exact and directly satisfy the user requirement.

---

## 4. Integration Blueprint with Existing Modules

### 4.1 Interface with `src/pipeline.py` (`MarketPredictionEngine`)
In `src/pipeline.py`, replace hardcoded values with `HorizonParameters`:
```python
# Before (src/pipeline.py:113-114):
def analyze_ticker(self, ticker: str, period: str = "2y", interval: str = "1d", ...):

# After:
def analyze_ticker(
    self, 
    ticker: str, 
    horizon_params: Optional[HorizonParameters] = None,
    ...
):
    params = horizon_params or HorizonMapper.get_parameters("1 day")
    period = params.lookback_period
    interval = params.bar_interval
    # Pass params.annualization_factor to TechnicalFeaturePipeline & MarketRegimeClassifier
    # Pass params.pt_vol_mult, params.sl_vol_mult to MetaLabelingEngine
    # Pass params.tcn_seq_len, params.tcn_horizon_bars to TorchSequenceForecaster
```

### 4.2 Interface with `src/execution/frictions.py` (`FrictionEvaluator`)
```python
# Pass is_intraday based on horizon_params.is_intraday_friction:
frictions_bps = FrictionEvaluator.calculate_round_trip_friction_bps(
    ticker=ticker,
    is_intraday=horizon_params.is_intraday_friction,
    reference_price=current_price,
    order_notional=order_notional,
    daily_dollar_volume=adv,
    annualized_vol=vol_annualized,
)
```

### 4.3 Interface with `src/execution/live_bot.py` (`LiveBotController`)
In `LiveBotController`, replace lines 992–1013:
```python
# Before:
vol_bar = max(r.volatility_cone.expected_vol_annualized / np.sqrt(252.0), 0.012)
pt_p = round(ref_entry_p * (1.0 + 1.4 * vol_bar), decimals)
sl_p = round(ref_entry_p * (1.0 - 1.0 * vol_bar), decimals)

# After:
params = self.horizon_params  # Configured from session
vol_bar = max(r.volatility_cone.expected_vol_annualized / params.annualization_factor, params.vol_floor_bar)
pt_p = round(ref_entry_p * (1.0 + params.pt_vol_mult * vol_bar), decimals)
sl_p = round(ref_entry_p * (1.0 - params.sl_vol_mult * vol_bar), decimals)
```

### 4.4 Interface with Setup Wizard API (`server.py`)
In `server.py`, the recommendation endpoint calls `UniverseSelector`:
```python
@app.post("/api/sessions/recommendations")
async def get_recommendations(req: RecommendationRequest):
    selector = UniverseSelector()
    result = selector.auto_select_basket(market=req.market, target_size=req.target_size or 5)
    return result.to_dict()
```

---

## 5. Verification Strategy & Test Suites

The test suite consists of two dedicated modules:
1. `tests/test_strategy_universe_selector.py`
   - Gate 1: Data quality evaluation ($Q_{\text{data}}$ calculation, missing bar penalty, zero volume penalty).
   - Gate 2: ADV calculation and market-specific thresholds ($5M US, ₹50M NSE, $10M Crypto).
   - Gate 3: Spread calculation (live BBO, fallback estimation, 25 bps cutoff).
   - Gate 4: Volatility bounds (rejection of <8% and >100% vol, acceptance of 8%-100%).
   - Composite scoring: Monotonicity and factor weighting.
   - Basket auto-selection: Clamping (3 to 6), ranking order, graceful handling of zero passing candidates.
   - Rationale generation: Non-empty, informative text output for wizard.
2. `tests/test_strategy_horizon_mapper.py`
   - Canonical name normalization (`"1h"`, `"1 hour"`, `"intraday"` $\to$ `"1 hour"`).
   - Exact annualization factors: 140.2 (1h), 40.5 (1d), 15.87 (1wk).
   - Bar intervals, lookback periods, TCN lengths/horizons, and barrier multipliers.
   - Policy and friction flags (`CLOSE_POSITIONS` vs `KEEP_OPEN`, `is_intraday_friction`).
   - Immutability of `HorizonParameters` (`frozen=True`).
