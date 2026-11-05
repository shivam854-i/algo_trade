# Quantitative Strategy Engine Analysis Report: TradeEvaluator & TradeRanker (Milestone 1 - Part B)

**Author**: Quantitative Strategy Explorer (`teamwork_explorer`, m1_explorer_2)  
**Target Modules**: `src/strategy/trade_evaluator.py`, `src/strategy/trade_ranker.py`  
**Test Suites**: `tests/test_strategy_trade_evaluator.py`, `tests/test_strategy_trade_ranker.py`  
**Date**: November 5, 2026  
**Status**: Complete  

---

## Executive Summary

This report delivers the quantitative specification, mathematical derivations, data models, integration contracts, and test requirements for **Part B of Milestone 1** (`TradeEvaluator` and `TradeRanker`). 

In the legacy implementation (`src/execution/live_bot.py` lines 981–984), opportunities were ranked naively using the absolute difference of probability from 0.50:
```python
candidates.sort(
    key=lambda x: abs(x[1].meta_prediction.success_probability - 0.50),
    reverse=True,
)
```
This naive ranking method is fundamentally flawed for production algorithmic trading:
1. It ignores payoff asymmetry ($b = \mathbb{E}[\text{Win}] / \mathbb{E}[\text{Loss}]$). A trade with $p=0.55$ and a $3:1$ reward-to-risk ratio has vastly higher mathematical expectancy than a trade with $p=0.60$ and an inverted $1:3$ ratio.
2. It ignores sample-size and forecast uncertainty, treating an estimate from 30 bars identically to one from 250 bars.
3. It ignores execution friction costs (statutory exchange fees, STT/GST, SEC Section 31, and Almgren-Chriss market impact), frequently accepting trades where transaction costs exceed gross alpha.
4. It ignores market regime dynamics (State 0 Trending, State 1 Choppy, State 2 Crisis) and model consensus between the causal decision tree meta-labeler and the supervised causal TCN sequence model.

The new `TradeEvaluator` and `TradeRanker` modules replace this heuristic with a mathematically rigorous Net Expectancy framework incorporating epistemic uncertainty bounds, gap risk buffers, statutory frictions, regime-conditioned multipliers, and model synergy boosts.

---

## 1. TradeEvaluator Architecture & Mathematical Formulation

### 1.1 Net Expectancy Equation

The expected value ($\text{EV}$) of a prospective trade per dollar or unit of capital deployed is:

$$\text{EV} = P(\text{Win}) \cdot \mathbb{E}[\text{Win} \mid \text{Win}] - P(\text{Loss}) \cdot \mathbb{E}[\text{Loss} \mid \text{Loss}] - \text{Expected Friction Cost}$$

Where:
- All return quantities ($\mathbb{E}[\text{Win}]$, $\mathbb{E}[\text{Loss}]$, $\text{Friction}$, and $\text{EV}$) are expressed consistently in percentage points ($\%$).
- $P(\text{Win})$ is the uncertainty-penalized conservative win probability $p_{\text{conservative}}$.
- $P(\text{Loss}) = 1.0 - p_{\text{conservative}}$.
- $\text{Expected Friction Cost}$ is the round-trip friction and slippage cost computed by `FrictionEvaluator`.

A trade is deemed economically viable only if:
$$\text{EV} \ge \text{min\_ev\_hurdle\_pct} \quad (\text{default } +0.20\% = 20\text{ bps})$$
Any trade with $\text{EV} \le 0$ or $\text{EV} < 0.20\%$ is strictly rejected.

---

### 1.2 Epistemic Uncertainty Margin & Conservative Win Probability

Standard machine learning classification models output a point estimate $p \in [0.0, 1.0]$ representing the probability of the profit target barrier being touched prior to the stop loss. However, finite historical sample sizes and forecast dispersion introduce epistemic uncertainty into $p$.

We define the epistemic standard error $\sigma_p$ as:

$$\sigma_p = \sqrt{\frac{p(1 - p)}{\min(N_{\text{bars}}, 250)}} \cdot \left(1.0 + 0.2 \cdot \frac{q_{90} - q_{10}}{\max(|q_{50}|, 1e-4)}\right)$$

Where:
1. **Bernoulli Sampling Variance**:
   $$\text{SE}_{\text{Bernoulli}} = \sqrt{\frac{p(1 - p)}{N_{\text{eff}}}}, \quad N_{\text{eff}} = \max(\min(N_{\text{bars}}, 250), 10)$$
   $N_{\text{bars}}$ is the number of historical bars used for model fitting. Capping at 250 bars prevents overconfidence from non-stationary long-term data (approx. 1 trading year of daily bars), while clamping the denominator at $\ge 10$ prevents division by zero.
2. **Quantile Dispersion Penalty**:
   $$\text{Dispersion Multiplier} = 1.0 + 0.2 \cdot \frac{q_{90} - q_{10}}{\max(|q_{50}|, 1e-4)}$$
   - $q_{10}, q_{50}, q_{90}$ represent the 10th percentile, median (50th percentile), and 90th percentile expectations from the volatility cone or Causal TCN sequence forecaster.
   - The term $\frac{q_{90} - q_{10}}{|q_{50}|}$ is the inter-quantile dispersion normalized by central expectation. When forward trajectory uncertainty is high, the quantile envelope widens, amplifying $\sigma_p$.
   - $\max(|q_{50}|, 1e-4)$ guarantees numerical stability when median drift is zero or close to zero.
3. **Conservative Win Probability**:
   $$p_{\text{conservative}} = \min(\max(0.0, p - 1.0 \cdot \sigma_p), 1.0)$$
   A one-standard-error ($1.0 \cdot \sigma_p$) epistemic margin of safety is subtracted from the raw point probability $p$.
   - If sample size $N_{\text{bars}}$ is small or quantile dispersion is large, $\sigma_p$ is elevated, driving $p_{\text{conservative}}$ downward.
   - If epistemic uncertainty exceeds $p$, $p_{\text{conservative}}$ clamps to $0.0$, guaranteeing trade rejection.

---

### 1.3 Conditional Payoffs and Gap Risk Buffer

Let $P_{\text{entry}}$ denote the trade entry price, $P_{\text{target}}$ the profit-taking barrier, and $P_{\text{stop}}$ the stop-loss barrier.

#### A. Directional Barrier Returns
- **LONG Trade** ($P_{\text{target}} > P_{\text{entry}} > P_{\text{stop}}$):
  $$R_{\text{target}} = \frac{P_{\text{target}} - P_{\text{entry}}}{P_{\text{entry}}} \times 100\%$$
  $$R_{\text{stop}} = \frac{P_{\text{entry}} - P_{\text{stop}}}{P_{\text{entry}}} \times 100\%$$
- **SHORT Trade** ($P_{\text{target}} < P_{\text{entry}} < P_{\text{stop}}$):
  $$R_{\text{target}} = \frac{P_{\text{entry}} - P_{\text{target}}}{P_{\text{entry}}} \times 100\%$$
  $$R_{\text{stop}} = \frac{P_{\text{stop}} - P_{\text{entry}}}{P_{\text{entry}}} \times 100\%$$

#### B. Gap Risk Buffer ($\text{GapBuffer}$)
Stop-market execution in continuous markets experiences adverse slippage and gap-through during volatile spikes or overnight sessions. To capture this microstructure risk, an adverse gap buffer is added to the conditional loss:

$$\text{GapBuffer} = 0.10 \times \sigma_{\text{bar}} \times 100\%$$

Where:
- $\sigma_{\text{bar}}$ is the standard deviation of single-bar returns for the asset.
- If annualized volatility $\sigma_{\text{annual}}$ is provided:
  $$\sigma_{\text{bar}} = \frac{\sigma_{\text{annual}}}{\sqrt{\text{AnnualizationFactor}}}$$
  (e.g., $\sqrt{252} \approx 15.8745$ for daily bars, $40.5$ for 1-day/1h bars, $140.2$ for 1-hour/5m bars).
- Alternatively, $\sigma_{\text{bar}}$ is directly computed as the standard deviation of percentage returns over the last 30 bars of OHLCV data.

#### C. Expected Conditional Outcomes
$$\mathbb{E}[\text{Win} \mid \text{Win}] = R_{\text{target}}$$
$$\mathbb{E}[\text{Loss} \mid \text{Loss}] = R_{\text{stop}} + \text{GapBuffer}$$

This formulation guarantees that the potential downside is never underestimated.

---

### 1.4 Friction and Slippage Integration

The expected transaction friction is evaluated through `FrictionEvaluator` from `src/execution/frictions.py`:

```python
round_trip_bps = FrictionEvaluator.calculate_round_trip_friction_bps(
    ticker=ticker,
    is_intraday=is_intraday,
    reference_price=entry_price,
    include_slippage=True,
    order_notional=order_notional,  # Default: 10,000
    daily_dollar_volume=adv,  # From recent OHLCV or profile
    annualized_vol=annualized_vol,  # From VolatilityCone
)
round_trip_friction_pct = round_trip_bps / 100.0  # 100 bps = 1.0%
```

`FrictionEvaluator` includes:
1. **Statutory Taxes & Exchange Fees**:
   - US Equities: SEC Section 31 ($0.0000278$ sell), FINRA TAF ($0.000015$), broker per-share normalization ($(\$0.005 \times 2) / P_{\text{entry}}$).
   - NSE Cash: Holding-period aware delivery STT ($0.10\%$ buy + sell) vs intraday STT ($0.025\%$ sell), NSE exchange turnover charge ($0.00325\%$), SEBI turnover charge ($0.0001\%$), Stamp Duty ($0.015\%$ delivery buy vs $0.003\%$ intraday buy), and 18% GST on brokerage + exchange + SEBI fees.
   - Crypto, Forex, Commodity schedules with appropriate taker and exchange fees.
2. **Almgren-Chriss Temporary Market Impact Slippage**:
   $$\text{Slippage}_{\text{RT}} = 2 \times \left[ \text{HalfSpread} \times \text{RolloverMult} + \eta \cdot \sigma_{\text{daily}} \cdot \sqrt{\frac{Q_{\text{order}}}{\text{ADV}}} \times 10^4 \right]$$
3. **Microstructure Execution Gates**:
   Before computing EV, `TradeEvaluator` verifies `FrictionEvaluator.check_microstructure_execution_gate(ticker, ohlcv_df)`:
   - Forex 17:00 EST (21:00 UTC) rollover liquidity trough (400% spread spike).
   - CME Commodity LULD velocity shock ($>5.5\%$ single-bar return).
   - Liquidity-sweep / stop-run exhaustion wicks ($>78\%$ wick rejection on $>2.6\times$ median range).
   If any microstructure gate fails, the trade is immediately rejected.

---

### 1.5 TradeEvaluationResult Data Structure Specification

```python
@dataclass
class TradeEvaluationResult:
  ticker: str
  direction: str  # "LONG" or "SHORT"
  entry_price: float
  target_price: float
  stop_price: float
  raw_win_prob: float  # Unadjusted point probability p
  epistemic_uncertainty: float  # sigma_p margin
  conservative_win_prob: float  # p_conservative = max(0, p - sigma_p)
  loss_probability: float  # 1.0 - p_conservative
  expected_win_return_pct: float  # E[Win | Win] in %
  expected_loss_return_pct: float  # E[Loss | Loss] in % (includes gap buffer)
  gap_risk_buffer_pct: float  # 0.10 * sigma_bar in %
  round_trip_friction_pct: float  # Statutory + Almgren-Chriss slippage in %
  gross_expectancy_pct: float  # p_cons * E[Win] - (1 - p_cons) * E[Loss]
  net_expectancy_pct: float  # EV = gross_expectancy_pct - friction_pct
  min_ev_hurdle_pct: float  # Hurdle threshold (e.g. 0.20%)
  is_positive_ev: bool  # True iff net_expectancy_pct >= min_ev_hurdle_pct
  rejection_reason: Optional[str] = None  # None if approved, else rationale
  payoff_ratio: float = (
      0.0  # b = E[Win] / max(E[Loss], 1e-4) (asymmetry ratio)
  )
  evaluation_metadata: Dict[str, Any] = field(default_factory=dict)
```

---

## 2. TradeRanker Architecture & Multiplier Framework

Once prospective opportunities are evaluated by `TradeEvaluator`, `TradeRanker` ranks them systematically to determine capital allocation priority.

### 2.1 Risk-Adjusted Value Calculation

To normalize expectancy across instruments with varying volatilities, raw net expectancy is scaled by asset volatility:

$$\text{Risk-Adjusted Value} = \frac{\text{EV}}{\max(\sigma_{\text{asset}}, 0.05)}$$

Where:
- $\text{EV}$ is `net_expectancy_pct` (e.g., $+0.65\%$).
- $\sigma_{\text{asset}}$ is the annualized asset volatility (e.g., $0.20 = 20\%$). Clamping at $\ge 0.05$ prevents division by near-zero for ultra-stable instruments.
- This formulation represents an expected value-to-risk ratio (akin to an annualized trade-level Information Ratio or Sharpe edge).

---

### 2.2 Market Regime Alignment Multipliers

Market regimes are classified by the Causal Forward-Filtering Hidden Markov Model (`src/models/regime_hmm.py`) into three discrete states:

| State ID | Regime Name | Multiplier | Condition | Action |
|---|---|---|---|---|
| **State 0** | Low-Vol Trending | **$1.25\times$** | Direction aligns with prevailing trend | Boost composite score by 25% |
| **State 0** | Low-Vol Trending | **$1.00\times$** | Counter-trend trade | Neutral multiplier |
| **State 1** | Choppy Range-Bound | **$1.15\times$** | Mean-reverting trade setup | Boost composite score by 15% |
| **State 1** | Choppy Range-Bound | **$1.00\times$** | Non-mean-reverting trade | Neutral multiplier |
| **State 2** | High-Vol Crisis | **$0.00\times$** | Any trade direction | **HARD VETO**: Score forced to 0.0, marked ineligible |

#### Identification of Alignment
- **Trend Alignment in State 0**:
  - A LONG trade is trend-aligned if the asset is in an upward trend (e.g., `Close > EMA50`, `EMA20 > EMA50`, or `analysis.meta_prediction.primary_direction == 1`).
  - A SHORT trade is trend-aligned if the asset is in a downward trend (e.g., `Close < EMA50`, `EMA20 < EMA50`, or `analysis.meta_prediction.primary_direction == -1`).
  - Trend-aligned trades receive the **$1.25\times$** boost.
- **Mean-Reversion Alignment in State 1**:
  - A LONG trade is mean-reverting if the asset is oversold (e.g., `RSI < 45` or `Z_Score < -0.5` or price near lower Bollinger band).
  - A SHORT trade is mean-reverting if the asset is overbought (e.g., `RSI > 55` or `Z_Score > 0.5` or price near upper Bollinger band).
  - Mean-reverting setups in choppy regimes receive the **$1.15\times$** boost.
- **Crisis Hard Veto in State 2**:
  - State 2 triggers an absolute capital preservation veto: `regime_multiplier = 0.0`, `is_eligible = False`, `ineligible_reason = "Hard veto: Market regime is State 2 (Crisis) with elevated tail risk"`.

---

### 2.3 Model Synergy Boost ($1.15\times$)

The platform features two distinct algorithmic prediction paradigms:
1. **Purged Tabular Meta-Labeler** (LightGBM decision trees on fractional and technical features).
2. **Supervised Causal Quantile TCN** (Dilated 1D convolutional network with Pinball loss on 5-channel geometric price sequences).

When both independent models show strong directional agreement:
- For **LONG** trades: Meta-model indicates Long (`primary_direction == 1` with `raw_win_prob >= 0.55`) AND Causal TCN directional conviction `neural_prob >= 0.60`.
- For **SHORT** trades: Meta-model indicates Short (`primary_direction == -1` with `raw_win_prob >= 0.55`) AND Causal TCN directional conviction `neural_prob <= 0.40`.

When this condition is satisfied:
$$\text{Synergy Boost} = 1.15$$
Otherwise:
$$\text{Synergy Boost} = 1.00$$

---

### 2.4 Composite Score & Ranking Procedure

The composite opportunity score is computed as:

$$\text{Composite Score} = \text{Risk-Adjusted Value} \times \text{Regime Multiplier} \times \text{Synergy Boost}$$

#### Sorting & Partitioning Algorithm
1. **Partition into Eligible and Ineligible Groups**:
   - **Eligible Trades**: `evaluation.is_positive_ev == True` AND `regime_multiplier > 0.0` (i.e., not in State 2 Crisis).
   - **Ineligible Trades**: `evaluation.is_positive_ev == False` OR `regime_multiplier == 0.0` OR microstructure failure.
2. **Sort Within Groups**:
   - Sort eligible trades by `composite_score` **descending**. Break ties by `net_expectancy_pct` descending, then ticker alphabetically.
   - Sort ineligible trades by `composite_score` **descending** (or `net_expectancy_pct` descending).
3. **Concatenate & Rank**:
   - `all_ranked = eligible_trades + ineligible_trades`
   - Assign integer ranks $1, 2, \dots, N$. All eligible trades strictly outrank ineligible trades.
4. **RankedOpportunity Data Structure**:
```python
@dataclass
class RankedOpportunity:
  rank: int  # 1-indexed rank
  ticker: str
  direction: str  # "LONG" or "SHORT"
  evaluation: TradeEvaluationResult
  risk_adjusted_value: float  # EV / sigma_asset
  regime_multiplier: (
      float  # 1.25 (Trending), 1.15 (Choppy), 0.0 (Crisis veto), 1.0 (Neutral)
  )
  synergy_boost: float  # 1.15 (TCN + Meta agreement) or 1.0
  composite_score: (
      float  # risk_adjusted_value * regime_multiplier * synergy_boost
  )
  is_eligible: bool  # True if eligible for capital allocation
  ineligible_reason: Optional[str] = (
      None  # Reason if ineligible, else None
  )
  rank_justification: str = ""  # Plain-language explanation of ranking
```

---

## 3. Integration Contracts

```
[SingleAssetAnalysis] + [HorizonParameters]
           │
           ▼
   ┌──────────────────┐
   │  TradeEvaluator  │ ◄─── FrictionEvaluator (Statutory & Almgren-Chriss)
   └──────────────────┘
           │
     TradeEvaluationResult (Net Expectancy, p_conservative, Frictions, Hurdle)
           │
           ▼
   ┌──────────────────┐
   │   TradeRanker    │ ◄─── RegimeState (HMM 0/1/2) & TCN Neural Conviction
   └──────────────────┘
           │
     List[RankedOpportunity] (Sorted Descending, Eligible/Ineligible)
           │
           ├─────────────────────────────────────────┐
           ▼                                         ▼
   ┌───────────────────────┐             ┌───────────────────────┐
   │   PortfolioSelector   │             │   DecisionExplainer   │
   │  (Fractional Kelly/   │             │ (Plain-Language Log & │
   │  HRP / 100% Cash)     │             │ UI Activity Feed)     │
   └───────────────────────┘             └───────────────────────┘
```

### 3.1 Interface Contract with `PortfolioSelector`
- `PortfolioSelector.allocate(ranked_opportunities, total_virtual_equity, ...)` consumes `List[RankedOpportunity]`.
- **100% Cash Allocation Guarantee**: If `len(ranked_opportunities) == 0` or all opportunities have `is_eligible == False` (zero positive net expectancy trades), `PortfolioSelector` immediately returns:
  `weights={"CASH": 1.0}`, `cash_weight=1.0`, `is_100_percent_cash=True`.

### 3.2 Interface Contract with `DecisionExplainer`
- `DecisionExplainer.explain_opportunity(ranked_opportunity)` consumes `RankedOpportunity` to produce plain-language justifications showing:
  - Calculated Net Expectancy and breakdown ($P(\text{Win})$, $P(\text{Loss})$, frictions deducted).
  - Risk-adjusted ranking score and applied multipliers (Regime alignment, Synergy boost).
  - Rejection rationale if ineligible.

---

## 4. Test Specifications & Verification Strategy

### 4.1 `tests/test_strategy_trade_evaluator.py`
Unit and invariant test cases covering:
1. **Mathematical Invariant: Analytical Net Expectancy Formula**:
   - Given controlled inputs ($P=0.60$, $R_{\text{target}}=3.0\%$, $R_{\text{stop}}=1.5\%$, $\text{Friction}=0.25\%$, $\sigma_p=0.0$), verify $\text{EV} = 0.60 \times 3.0 - 0.40 \times 1.5 - 0.25 = 1.80 - 0.60 - 0.25 = 0.95\%$.
2. **Epistemic Uncertainty Margin**:
   - Verify $\sigma_p$ increases when $N_{\text{bars}}$ decreases (e.g. $N=30$ vs $N=250$).
   - Verify $\sigma_p$ increases when quantile spread $(q_{90} - q_{10})$ expands.
   - Verify $p_{\text{conservative}} = \max(0.0, p - \sigma_p)$ never goes negative.
3. **Gap Risk Buffer**:
   - Verify $\mathbb{E}[\text{Loss} \mid \text{Loss}] = R_{\text{stop}} + 0.10 \times \sigma_{\text{bar}}$ for both LONG and SHORT.
4. **Friction Hurdle Enforcement**:
   - Test trade with gross edge $+0.30\%$ and statutory friction $+0.40\% \implies \text{EV} < 0$, must be rejected.
   - Test trade with $\text{EV} = +0.15\% < 0.20\%$ hurdle $\implies$ rejected with below-hurdle reason.
   - Test trade with $\text{EV} = +0.45\% \ge 0.20\%$ hurdle $\implies$ accepted.
5. **Microstructure Gate Veto**:
   - Verify that Forex 17:00 EST rollover or CME Gold LULD triggers automatic trade rejection.
6. **SHORT Trade Mechanics**:
   - Verify correct profit and stop return calculation when direction is SHORT ($P_{\text{target}} < P_{\text{entry}} < P_{\text{stop}}$).

### 4.2 `tests/test_strategy_trade_ranker.py`
Unit and invariant test cases covering:
1. **Risk-Adjusted Value**:
   - Compare two trades with identical $\text{EV} = +1.0\%$, asset A has $\sigma=0.10$, asset B has $\sigma=0.25$. Verify asset A receives higher risk-adjusted value ($0.10$ vs $0.04$).
2. **Regime Multipliers**:
   - State 0 Trending: Verify trend-aligned trade receives $1.25\times$ boost.
   - State 1 Choppy: Verify mean-reverting trade receives $1.15\times$ boost.
   - State 2 Crisis: Verify $0.0\times$ hard veto, score forced to 0.0, `is_eligible = False`.
3. **Model Synergy Boost**:
   - Verify trade with both meta-model and TCN indicating Long ($\ge 0.60$) receives $1.15\times$ boost.
   - Verify trade with diverging models receives $1.00\times$.
4. **Sorting Invariant**:
   - Verify eligible trades always appear before ineligible trades.
   - Verify composite score ordering is strictly monotonic descending.
5. **Edge Cases**:
   - Empty input list returns empty list `[]`.
   - All opportunities ineligible returns all ranked with `is_eligible = False`.
   - Zero positive EV trades handled cleanly without exceptions.
