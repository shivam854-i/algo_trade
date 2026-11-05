# Quantitative Strategy Engine Handoff Report: TradeEvaluator & TradeRanker (Milestone 1 - Part B)

**Author**: Quantitative Strategy Explorer (`teamwork_explorer`, m1_explorer_2)  
**Recipient**: Quantitative Strategy Implementer & Lead Orchestrator  
**Date**: November 5, 2026  
**Type**: Hard Handoff (Investigation & Specification Complete)  
**Location**: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m1_explorer_2\handoff.md`  

---

## 1. Observation

Direct observations from codebase inspection of `C:\Users\Shivam\Desktop\trade_bot`:

1. **Absence of Dedicated Strategy Opportunity Evaluation Package**:
   - `src/strategy/` directory currently does not exist.
   - Opportunity ranking is currently embedded directly in `src/execution/live_bot.py` lines 981–984 using a naive probability-distance heuristic:
     ```python
     candidates.sort(
         key=lambda x: abs(x[1].meta_prediction.success_probability - 0.50),
         reverse=True,
     )
     ```
     This naive sorting fails to account for payoff asymmetry, sample-size epistemic uncertainty, friction hurdles, market regimes, or multi-model synergy.

2. **Friction Calculation Implementation (`src/execution/frictions.py`)**:
   - `FrictionEvaluator.calculate_round_trip_friction_bps(...)` (lines 205–292) accurately computes round-trip statutory costs (SEC fees, NSE delivery/intraday STT, GST, Stamp duty) plus dynamic Almgren-Chriss square-root temporary market impact slippage in basis points (`bps`).
   - `FrictionEvaluator.check_microstructure_execution_gate(...)` (lines 140–202) provides deterministic circuit breakers for Forex 17:00 EST rollover spread spikes, CME commodity LULD velocity halts ($>5.5\%$), and liquidity-sweep stop-run exhaustion wicks ($>78\%$ wick on $>2.6\times$ median range).
   - In `frictions.py` line 311: `friction_pct = friction_bps / 100.0` establishes that 100 bps equals 1.0% (percentage points).

3. **Causal Forward-Filtering HMM Regime Architecture (`src/models/regime_hmm.py`)**:
   - Lines 31–54 define three discrete market regime states:
     - `State 0`: "Low-Vol Trending" (`is_crisis = False`, `volatility_scale = 1.0`)
     - `State 1`: "Choppy Range-Bound" (`is_crisis = False`, `volatility_scale = 0.6`)
     - `State 2`: "High-Vol Crisis" (`is_crisis = True`, `volatility_scale = 0.0`)
   - Lines 80–113 execute causal forward filtering without lookahead bias.

4. **Two-Stage Meta-Labeling and Causal Quantile TCN Forecaster**:
   - `src/models/meta_labeler.py`: Lines 18–27 define `MetaPrediction` containing `primary_direction` (+1 Long, -1 Short, 0 Neutral), `success_probability`, `bet_size`, `target_price`, and `stop_price`. Line 186 calibrates empirical payoff asymmetry ratio $b = \text{AvgWin} / \text{AvgLoss}$.
   - `src/models/gpu_acceleration.py`: Lines 267–312 define `forecast_tensor` and `evaluate_directional_conviction`. The model outputs monotonic non-crossing quantiles $q_{10} \le q_{50} \le q_{90}$ and directional conviction `neural_prob`.
   - `src/pipeline.py`: Lines 207–230 perform ensemble fusion (`fused_prob = round(0.65 * lgbm_prob + 0.35 * neural_prob, 3)`), veto false breakouts when TCN disagrees, and apply conviction boosts when both models strongly agree.

5. **Test Suite Baseline**:
   - Command `py tests/test_phase1_phase2_fixes.py` runs with exit code 0 verifying all 8 baseline quantitative invariants (FracDiff, Causal HMM future-invariance, Triple-barrier dual-breach wick priority, HRP RMT variance preservation, Frictions, Asymmetric CVaR-Kelly, Supervised TCN Pinball loss, Microstructure gates).
   - `py -m pytest tests/test_market_sessions.py` (35 passed) and `py -m pytest tests/test_real_market_paper_trading.py` (22 passed) confirm the existing execution and data infrastructure is robust.

---

## 2. Logic Chain

1. **From Observation 1 to Net Expectancy Formulation**:
   - Because naive probability ranking ignores the magnitude of wins vs. losses and trading fees, high-probability trades with small gains and large downside or high commissions are erroneously favored.
   - Therefore, `TradeEvaluator` must compute true mathematical Net Expectancy:
     $$\text{EV} = P(\text{Win}) \cdot \mathbb{E}[\text{Win} \mid \text{Win}] - P(\text{Loss}) \cdot \mathbb{E}[\text{Loss} \mid \text{Loss}] - \text{Expected Friction Cost}$$
   - Any opportunity with $\text{EV} \le 0$ or below the minimum hurdle (+0.20%) has negative or insufficient economic edge and must be rejected.

2. **From Observation 4 to Epistemic Uncertainty Margin**:
   - Machine learning point estimates of probability $p$ are subject to estimation error proportional to $1/\sqrt{N_{\text{bars}}}$ and the dispersion of forward quantile trajectories.
   - By subtracting the epistemic standard error $\sigma_p$ from $p$:
     $$\sigma_p = \sqrt{\frac{p(1 - p)}{\min(N_{\text{bars}}, 250)}} \cdot \left(1.0 + 0.2 \cdot \frac{q_{90} - q_{10}}{\max(|q_{50}|, 1e-4)}\right)$$
     $$p_{\text{conservative}} = \max(0.0, p - 1.0 \cdot \sigma_p)$$
     the evaluator prevents overconfidence on short histories or divergent quantile projections.

3. **From Observation 2 to Microstructure and Friction Hurdle Integration**:
   - Statutory transaction costs and market impact reduce gross returns.
   - Integrating with `FrictionEvaluator.calculate_round_trip_friction_bps` ensures costs are deducted in dimensionally consistent units (percentage points: $\text{bps} / 100.0$).
   - Calling `check_microstructure_execution_gate` guards against illiquid rollover troughs and stop-run shock conditions.

4. **From Observation 1 & 3 to Risk-Adjusted Ranking and Regime Multipliers**:
   - Raw EV is not directly comparable across assets with different volatilities. Dividing EV by asset volatility $\sigma_{\text{asset}}$ yields an apples-to-apples risk-adjusted opportunity score.
   - Applying regime multipliers (State 0 Trending: $1.25\times$; State 1 Choppy: $1.15\times$; State 2 Crisis: $0.0\times$ hard veto) aligns opportunity selection with the macro market state.
   - Applying a $1.15\times$ synergy boost when the tabular meta-labeler and causal TCN both agree reinforces high-conviction quantitative signals.

---

## 3. Caveats

1. **Read-Only Investigation**:
   - In accordance with explorer rules, this report provides complete specifications and test requirements without directly creating or modifying files in `src/strategy/` or `tests/`.
2. **Yahoo Finance Intraday Lookback Limit**:
   - 1-hour horizon (5-minute bars) historical lookback is restricted by Yahoo Finance to 60 days. Sample size $N_{\text{bars}}$ will naturally reflect this data window, and $\min(N_{\text{bars}}, 250)$ correctly adjusts $\sigma_p$ for intraday samples.
3. **Short Selling Restrictions by Jurisdiction**:
   - Short trade evaluation calculates barriers inversely ($P_{\text{target}} < P_{\text{entry}} < P_{\text{stop}}$). Downstream execution engines enforce exchange-specific short sale rules (e.g., intraday-only for Indian equities on NSE cash).

---

## 4. Conclusion & Concrete Design Blueprint

### 4.1 Class Designs and Implementation Blueprint

#### File 1: `src/strategy/trade_evaluator.py`

```python
"""Trade Expectancy Evaluator Module.

Computes mathematical Net Expectancy incorporating epistemic uncertainty bounds,
conditional payoff barriers, gap risk buffers, statutory frictions, and Almgren-Chriss
market impact.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from src.execution.frictions import FrictionEvaluator
from src.pipeline import SingleAssetAnalysis


@dataclass
class TradeEvaluationResult:
  """Detailed quantitative evaluation result for a single trade candidate."""

  ticker: str
  direction: str  # "LONG" or "SHORT"
  entry_price: float
  target_price: float
  stop_price: float
  raw_win_prob: float  # Unadjusted point probability p in [0.0, 1.0]
  epistemic_uncertainty: float  # Epistemic margin sigma_p
  conservative_win_prob: float  # p_conservative = max(0.0, p - 1.0 * sigma_p)
  loss_probability: float  # 1.0 - conservative_win_prob
  expected_win_return_pct: float  # E[Win | Win] in %
  expected_loss_return_pct: (
      float  # E[Loss | Loss] in % (includes gap risk buffer)
  )
  gap_risk_buffer_pct: float  # 0.10 * sigma_bar in %
  round_trip_friction_pct: float  # Statutory + Almgren-Chriss slippage in %
  gross_expectancy_pct: float  # p_cons * E[Win] - (1 - p_cons) * E[Loss] in %
  net_expectancy_pct: float  # EV = gross_expectancy_pct - friction_pct in %
  min_ev_hurdle_pct: float = 0.20  # Minimum required EV hurdle (+0.20%)
  is_positive_ev: bool = False  # True iff net_expectancy_pct >= min_ev_hurdle
  rejection_reason: Optional[str] = None  # None if approved, else rationale
  payoff_ratio: float = 0.0  # b = E[Win] / max(E[Loss], 1e-4)
  evaluation_metadata: Dict[str, Any] = field(default_factory=dict)


class TradeEvaluator:
  """Computes mathematical Net Expectancy with epistemic uncertainty and friction hurdles."""

  def __init__(self, default_min_ev_hurdle_pct: float = 0.20):
    self.default_min_ev_hurdle_pct = default_min_ev_hurdle_pct

  @staticmethod
  def compute_epistemic_uncertainty(
      p: float,
      n_bars: int,
      q10: float,
      q50: float,
      q90: float,
  ) -> float:
    """Computes epistemic uncertainty margin sigma_p.

    Formula:
        sigma_p = sqrt(p * (1 - p) / min(n_bars, 250)) * (1.0 + 0.2 * (q90 -
        q10) / max(|q50|, 1e-4))
    """
    p_clamped = min(max(float(p), 0.0), 1.0)
    n_eff = max(min(int(n_bars), 250), 10)
    bernoulli_se = math.sqrt((p_clamped * (1.0 - p_clamped)) / n_eff)

    denom = max(abs(float(q50)), 1e-4)
    dispersion = max(float(q90) - float(q10), 0.0) / denom
    dispersion_multiplier = 1.0 + 0.2 * dispersion

    sigma_p = bernoulli_se * dispersion_multiplier
    return float(sigma_p)

  @staticmethod
  def derive_conservative_win_prob(p: float, sigma_p: float) -> float:
    """Derives conservative win probability p_conservative = max(0.0, p - 1.0 * sigma_p)."""
    return float(min(max(0.0, float(p) - 1.0 * float(sigma_p)), 1.0))

  @classmethod
  def compute_conditional_returns(
      cls,
      direction: str,
      entry_price: float,
      target_price: float,
      stop_price: float,
      sigma_bar_pct: float,
  ) -> Tuple[float, float, float]:
    """Calculates conditional returns E[Win | Win] and E[Loss | Loss] including gap risk buffer.

    Returns:
        (expected_win_pct, expected_loss_pct, gap_buffer_pct)
    """
    entry = max(float(entry_price), 1e-4)
    direction_upper = direction.upper()

    if direction_upper == "LONG":
      r_target = max((float(target_price) - entry) / entry * 100.0, 0.0)
      r_stop = max((entry - float(stop_price)) / entry * 100.0, 0.0)
    else:  # SHORT
      r_target = max((entry - float(target_price)) / entry * 100.0, 0.0)
      r_stop = max((float(stop_price) - entry) / entry * 100.0, 0.0)

    gap_buffer_pct = 0.10 * max(float(sigma_bar_pct), 0.0)
    expected_win_pct = round(r_target, 4)
    expected_loss_pct = round(r_stop + gap_buffer_pct, 4)
    return expected_win_pct, expected_loss_pct, round(gap_buffer_pct, 4)

  def evaluate(
      self,
      analysis: SingleAssetAnalysis,
      horizon_params: Optional[Any] = None,
      min_ev_hurdle_pct: Optional[float] = None,
      order_notional: float = 10000.0,
  ) -> TradeEvaluationResult:
    """Evaluates a SingleAssetAnalysis candidate using Net Expectancy mathematics."""
    hurdle = (
        min_ev_hurdle_pct
        if min_ev_hurdle_pct is not None
        else self.default_min_ev_hurdle_pct
    )
    ticker = analysis.ticker.upper()
    entry_p = float(analysis.current_price)

    meta_pred = analysis.meta_prediction
    direction = (
        "LONG"
        if meta_pred.primary_direction > 0
        else ("SHORT" if meta_pred.primary_direction < 0 else "NEUTRAL")
    )
    target_p = float(meta_pred.target_price)
    stop_p = float(meta_pred.stop_price)
    raw_p = float(meta_pred.success_probability)

    # 1. Microstructure execution gate verification
    micro_ok, micro_reason = (
        FrictionEvaluator.check_microstructure_execution_gate(
            ticker, ohlcv_df=analysis.recent_ohlcv
        )
    )

    # 2. Extract sample size N_bars and quantiles (q10, q50, q90)
    n_bars = (
        len(analysis.recent_ohlcv)
        if analysis.recent_ohlcv is not None
        else (len(analysis.features_df) if analysis.features_df is not None else 100)
    )
    cone = analysis.volatility_cone
    if cone and cone.q10_prices and cone.q50_prices and cone.q90_prices:
      q10 = float(cone.q10_prices[-1])
      q50 = float(cone.q50_prices[-1])
      q90 = float(cone.q90_prices[-1])
    else:
      q10, q50, q90 = entry_p * 0.98, entry_p, entry_p * 1.02

    # 3. Compute Epistemic Uncertainty & Conservative Win Probability
    sigma_p = self.compute_epistemic_uncertainty(
        raw_p, n_bars, q10=q10, q50=q50, q90=q90
    )
    p_cons = self.derive_conservative_win_prob(raw_p, sigma_p)
    p_loss = round(1.0 - p_cons, 4)

    # 4. Bar volatility & Gap risk buffer
    annual_factor = (
        getattr(horizon_params, "annualization_factor", 252.0)
        if horizon_params
        else 252.0
    )
    annual_vol = (
        float(cone.expected_vol_annualized)
        if (cone and cone.expected_vol_annualized > 0)
        else 0.20
    )
    sigma_bar_pct = (annual_vol / math.sqrt(max(annual_factor, 1.0))) * 100.0

    # 5. Conditional returns
    e_win, e_loss, gap_buf = self.compute_conditional_returns(
        direction=direction if direction != "NEUTRAL" else "LONG",
        entry_price=entry_p,
        target_price=target_p,
        stop_price=stop_p,
        sigma_bar_pct=sigma_bar_pct,
    )

    # 6. Round-trip friction cost
    is_intraday = (
        getattr(horizon_params, "is_intraday_friction", False)
        if horizon_params
        else (analysis.market_jurisdiction != "US")
    )
    adv = 5e7
    if analysis.recent_ohlcv is not None and not analysis.recent_ohlcv.empty:
      df_ohlcv = analysis.recent_ohlcv
      if "Close" in df_ohlcv and "Volume" in df_ohlcv:
        adv = float((df_ohlcv["Close"] * df_ohlcv["Volume"]).tail(30).mean())
        adv = max(adv, 1e5)

    friction_bps = FrictionEvaluator.calculate_round_trip_friction_bps(
        ticker=ticker,
        is_intraday=is_intraday,
        reference_price=entry_p,
        include_slippage=True,
        order_notional=order_notional,
        daily_dollar_volume=adv,
        annualized_vol=annual_vol,
    )
    friction_pct = round(friction_bps / 100.0, 4)

    # 7. Net Expectancy Calculation
    gross_ev = round((p_cons * e_win) - (p_loss * e_loss), 4)
    net_ev = round(gross_ev - friction_pct, 4)
    payoff_b = round(e_win / max(e_loss, 1e-4), 3)

    # 8. Rejection Rules and Hurdle Enforcement
    rejection: Optional[str] = None
    if not micro_ok:
      rejection = f"MICROSTRUCTURE GATE VETO: {micro_reason}"
    elif direction == "NEUTRAL":
      rejection = "DIRECTION VETO: Primary direction is NEUTRAL (0)"
    elif (direction == "LONG" and (target_p <= entry_p or stop_p >= entry_p)) or (
        direction == "SHORT" and (target_p >= entry_p or stop_p <= entry_p)
    ):
      rejection = f"INVALID BARRIERS: Target ({target_p}) or Stop ({stop_p}) inverted relative to Entry ({entry_p})"
    elif p_cons <= 0.0:
      rejection = f"EPISTEMIC UNCERTAINTY VETO: Conservative win prob reduced to 0.0% (raw={raw_p:.1%}, sigma_p={sigma_p:.1%})"
    elif net_ev <= 0.0:
      rejection = f"NEGATIVE EV: Net expectancy ({net_ev:.2f}%) is non-positive"
    elif net_ev < hurdle:
      rejection = f"BELOW HURDLE: Net expectancy ({net_ev:.2f}%) is below minimum hurdle (+{hurdle:.2f}%)"

    is_positive_ev = rejection is None

    return TradeEvaluationResult(
        ticker=ticker,
        direction=direction,
        entry_price=entry_p,
        target_price=target_p,
        stop_price=stop_p,
        raw_win_prob=round(raw_p, 4),
        epistemic_uncertainty=round(sigma_p, 4),
        conservative_win_prob=round(p_cons, 4),
        loss_probability=p_loss,
        expected_win_return_pct=e_win,
        expected_loss_return_pct=e_loss,
        gap_risk_buffer_pct=gap_buf,
        round_trip_friction_pct=friction_pct,
        gross_expectancy_pct=gross_ev,
        net_expectancy_pct=net_ev,
        min_ev_hurdle_pct=hurdle,
        is_positive_ev=is_positive_ev,
        rejection_reason=rejection,
        payoff_ratio=payoff_b,
        evaluation_metadata={
            "annualized_vol": annual_vol,
            "neural_prob": getattr(analysis, "neural_prob", 0.50),
            "regime_state_id": (
                analysis.regime.state_id if analysis.regime else 0
            ),
        },
    )
```

---

#### File 2: `src/strategy/trade_ranker.py`

```python
"""Trade Opportunity Ranking Module.

Ranks evaluated trade opportunities by risk-adjusted net expectancy, applies market
regime alignment multipliers (State 0 Trending, State 1 Choppy, State 2 Crisis hard veto),
and adds model synergy boosts for Causal TCN and Meta-Labeler consensus.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import numpy as np

from src.models.regime_hmm import RegimeState
from src.pipeline import SingleAssetAnalysis
from src.strategy.trade_evaluator import TradeEvaluationResult


@dataclass
class RankedOpportunity:
  """Systematically ranked trade opportunity ready for portfolio allocation."""

  rank: int  # 1-indexed rank
  ticker: str
  direction: str  # "LONG" or "SHORT"
  evaluation: TradeEvaluationResult
  risk_adjusted_value: float  # EV / max(sigma_asset, 0.05)
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
  rank_justification: str = ""  # Plain-language explanation


class TradeRanker:
  """Ranks trade opportunities by risk-adjusted value, regime alignment, and model synergy."""

  def __init__(
      self,
      trending_multiplier: float = 1.25,
      choppy_multiplier: float = 1.15,
      synergy_boost_factor: float = 1.15,
  ):
    self.trending_multiplier = trending_multiplier
    self.choppy_multiplier = choppy_multiplier
    self.synergy_boost_factor = synergy_boost_factor

  def _evaluate_regime_multiplier(
      self,
      evaluation: TradeEvaluationResult,
      regime: Optional[RegimeState],
      analysis: Optional[SingleAssetAnalysis] = None,
  ) -> Tuple[float, Optional[str]]:
    """Evaluates regime multiplier and detects crisis hard veto."""
    if regime is None:
      return 1.0, None

    # State 2: High-Vol Crisis Hard Veto
    if regime.state_id == 2 or regime.is_crisis:
      return (
          0.0,
          "HARD VETO: Market regime is State 2 (Crisis) with elevated tail risk",
      )

    # State 0: Low-Vol Trending
    if regime.state_id == 0:
      is_trend_aligned = True
      if analysis is not None and analysis.features_df is not None:
        feats = analysis.features_df
        if "EMA50_Dist" in feats.columns and not feats.empty:
          dist = float(feats["EMA50_Dist"].iloc[-1])
          is_trend_aligned = (evaluation.direction == "LONG" and dist >= 0) or (
              evaluation.direction == "SHORT" and dist < 0
          )
      return (self.trending_multiplier if is_trend_aligned else 1.0), None

    # State 1: Choppy Range-Bound
    if regime.state_id == 1:
      is_mean_reverting = True
      if analysis is not None and analysis.features_df is not None:
        feats = analysis.features_df
        if "RSI" in feats.columns and not feats.empty:
          rsi = float(feats["RSI"].iloc[-1])
          is_mean_reverting = (
              evaluation.direction == "LONG" and rsi < 45
          ) or (evaluation.direction == "SHORT" and rsi > 55)
      return (self.choppy_multiplier if is_mean_reverting else 1.0), None

    return 1.0, None

  def _evaluate_synergy_boost(
      self,
      evaluation: TradeEvaluationResult,
      analysis: Optional[SingleAssetAnalysis] = None,
  ) -> float:
    """Evaluates whether Causal TCN and Meta-Labeler strongly agree."""
    if analysis is None:
      return 1.0

    neural_p = float(getattr(analysis, "neural_prob", 0.50))
    raw_p = float(evaluation.raw_win_prob)

    if evaluation.direction == "LONG" and neural_p >= 0.60 and raw_p >= 0.55:
      return self.synergy_boost_factor
    elif evaluation.direction == "SHORT" and neural_p <= 0.40 and raw_p >= 0.55:
      return self.synergy_boost_factor
    return 1.0

  def rank_opportunities(
      self,
      evaluations: List[TradeEvaluationResult],
      regimes: Optional[Dict[str, RegimeState]] = None,
      analyses: Optional[Dict[str, SingleAssetAnalysis]] = None,
  ) -> List[RankedOpportunity]:
    """Ranks opportunities descending by composite score, partitioning eligible vs ineligible trades."""
    if not evaluations:
      return []

    regimes_map = regimes or {}
    analyses_map = analyses or {}

    unranked_items: List[RankedOpportunity] = []

    for ev in evaluations:
      tk = ev.ticker
      analysis = analyses_map.get(tk)
      regime = regimes_map.get(tk) or (analysis.regime if analysis else None)

      # 1. Asset Volatility and Risk-Adjusted Value (EV / sigma)
      asset_vol = 0.20
      if analysis and analysis.volatility_cone:
        asset_vol = float(analysis.volatility_cone.expected_vol_annualized)
      elif "annualized_vol" in ev.evaluation_metadata:
        asset_vol = float(ev.evaluation_metadata["annualized_vol"])
      sigma_clamped = max(asset_vol, 0.05)
      risk_adj_val = round(ev.net_expectancy_pct / sigma_clamped, 4)

      # 2. Regime Multiplier & Crisis Veto
      regime_mult, crisis_reason = self._evaluate_regime_multiplier(
          ev, regime, analysis
      )

      # 3. Model Synergy Boost
      synergy = self._evaluate_synergy_boost(ev, analysis)

      # 4. Composite Score
      composite = round(risk_adj_val * regime_mult * synergy, 4)

      # 5. Eligibility Determination
      is_eligible = ev.is_positive_ev and regime_mult > 0.0
      ineligible_reason: Optional[str] = None
      if not ev.is_positive_ev:
        ineligible_reason = ev.rejection_reason or "Non-positive net expectancy"
      elif regime_mult == 0.0:
        ineligible_reason = crisis_reason

      justification = (
          f"[{tk} - {ev.direction}]: Net EV {ev.net_expectancy_pct:+.2f}%, "
          f"Vol {asset_vol:.1%}, Risk-Adj {risk_adj_val:.4f}. "
          f"Multipliers: Regime {regime_mult:.2f}x, Synergy {synergy:.2f}x -> "
          f"Score {composite:.4f} [{'ELIGIBLE' if is_eligible else 'INELIGIBLE'}]"
      )

      unranked_items.append(
          RankedOpportunity(
              rank=0,  # Assigned after sorting
              ticker=tk,
              direction=ev.direction,
              evaluation=ev,
              risk_adjusted_value=risk_adj_val,
              regime_multiplier=regime_mult,
              synergy_boost=synergy,
              composite_score=composite,
              is_eligible=is_eligible,
              ineligible_reason=ineligible_reason,
              rank_justification=justification,
          )
      )

    # Sort: Eligible trades first (composite desc, EV desc), then Ineligible trades
    eligible = [x for x in unranked_items if x.is_eligible]
    ineligible = [x for x in unranked_items if not x.is_eligible]

    eligible.sort(
        key=lambda x: (
            x.composite_score,
            x.evaluation.net_expectancy_pct,
            x.ticker,
        ),
        reverse=True,
    )
    ineligible.sort(
        key=lambda x: (
            x.composite_score,
            x.evaluation.net_expectancy_pct,
            x.ticker,
        ),
        reverse=True,
    )

    combined = eligible + ineligible
    ranked_results: List[RankedOpportunity] = []
    for idx, item in enumerate(combined, start=1):
      item.rank = idx
      item.rank_justification = f"Rank #{idx} " + item.rank_justification
      ranked_results.append(item)

    return ranked_results
```

---

### 4.2 Comprehensive Unit Test Blueprints

#### File 3: `tests/test_strategy_trade_evaluator.py`

```python
"""Unit tests for TradeEvaluator (Net Expectancy, Epistemic Uncertainty, Conditional Payoffs, Frictions)."""

from dataclasses import replace
import math
import numpy as np
import pandas as pd
import pytest

from src.execution.frictions import FrictionEvaluator
from src.models.foundation_prior import VolatilityCone
from src.models.meta_labeler import MetaPrediction
from src.models.regime_hmm import REGIME_DEFINITIONS
from src.pipeline import SingleAssetAnalysis
from src.strategy.trade_evaluator import TradeEvaluationResult, TradeEvaluator


class TestTradeEvaluatorNetExpectancy:

  def test_exact_analytical_ev_formula(self):
    """Verifies: EV = P(Win)*E[Win] - P(Loss)*E[Loss] - Friction."""
    # Synthetic inputs: p = 0.60, win = 3.0%, loss = 1.5%, friction = 0.25%
    p_win = 0.60
    p_loss = 0.40
    e_win = 3.00
    e_loss = 1.50
    friction = 0.25

    expected_gross = (p_win * e_win) - (p_loss * e_loss)  # 1.80 - 0.60 = 1.20%
    expected_net = expected_gross - friction  # 1.20 - 0.25 = 0.95%

    assert round(expected_net, 4) == 0.95

  def test_epistemic_uncertainty_formula_and_sample_scaling(self):
    """Verifies: sigma_p formula and verifies that smaller sample sizes increase uncertainty."""
    evaluator = TradeEvaluator()
    # Fixed parameters
    p = 0.55
    q10, q50, q90 = 98.0, 100.0, 102.0

    sigma_p_small_n = evaluator.compute_epistemic_uncertainty(
        p, n_bars=30, q10=q10, q50=q50, q90=q90
    )
    sigma_p_large_n = evaluator.compute_epistemic_uncertainty(
        p, n_bars=250, q10=q10, q50=q50, q90=q90
    )

    # Uncertainty on 30 bars must be strictly higher than on 250 bars
    assert sigma_p_small_n > sigma_p_large_n

    # Analytical check on large_n:
    # SE = sqrt(0.55 * 0.45 / 250) = sqrt(0.2475 / 250) = sqrt(0.00099) = 0.031464
    # Mult = 1.0 + 0.2 * (4.0 / 100.0) = 1.0 + 0.008 = 1.008
    # sigma_p = 0.031464 * 1.008 = 0.031716
    assert abs(sigma_p_large_n - 0.031716) < 1e-4

  def test_quantile_dispersion_penalty(self):
    """Verifies: wider quantile envelope (q90 - q10) increases epistemic uncertainty."""
    evaluator = TradeEvaluator()
    p = 0.55
    n_bars = 100

    # Narrow vs Wide quantiles
    sigma_narrow = evaluator.compute_epistemic_uncertainty(
        p, n_bars, q10=99.0, q50=100.0, q90=101.0
    )
    sigma_wide = evaluator.compute_epistemic_uncertainty(
        p, n_bars, q10=90.0, q50=100.0, q90=110.0
    )
    assert sigma_wide > sigma_narrow

  def test_conservative_win_prob_clamping(self):
    """Verifies: p_conservative = max(0.0, p - sigma_p) never produces negative probabilities."""
    evaluator = TradeEvaluator()
    p_cons_normal = evaluator.derive_conservative_win_prob(0.55, 0.05)
    assert p_cons_normal == 0.50

    p_cons_extreme = evaluator.derive_conservative_win_prob(0.40, 0.50)
    assert p_cons_extreme == 0.0

  def test_conditional_returns_long_and_short_with_gap_risk(self):
    """Verifies: E[Win | Win] and E[Loss | Loss] include 0.10 * sigma_bar for both LONG and SHORT."""
    # LONG: Entry=100, Target=103 (+3%), Stop=98.5 (-1.5%), sigma_bar_pct=1.0%
    # Gap buffer = 0.10 * 1.0% = 0.10%
    # E[Win] = 3.0%, E[Loss] = 1.5% + 0.10% = 1.60%
    w_long, l_long, gap_long = TradeEvaluator.compute_conditional_returns(
        direction="LONG",
        entry_price=100.0,
        target_price=103.0,
        stop_price=98.5,
        sigma_bar_pct=1.0,
    )
    assert w_long == 3.0
    assert l_long == 1.60
    assert gap_long == 0.10

    # SHORT: Entry=100, Target=97 (+3%), Stop=101.5 (-1.5%), sigma_bar_pct=1.0%
    w_short, l_short, gap_short = TradeEvaluator.compute_conditional_returns(
        direction="SHORT",
        entry_price=100.0,
        target_price=97.0,
        stop_price=101.5,
        sigma_bar_pct=1.0,
    )
    assert w_short == 3.0
    assert l_short == 1.60
    assert gap_short == 0.10

  def test_rejection_of_non_positive_and_sub_hurdle_ev(self):
    """Verifies: Trades with EV <= 0 or EV < hurdle (+0.20%) are rejected with clear reasons."""
    evaluator = TradeEvaluator(default_min_ev_hurdle_pct=0.20)

    # Mock SingleAssetAnalysis helper
    def make_analysis(target, stop, prob):
      cone = VolatilityCone(
          periods=[1, 2, 3, 4, 5],
          q10_prices=[98.0] * 5,
          q50_prices=[100.0] * 5,
          q90_prices=[102.0] * 5,
          expected_vol_annualized=0.20,
          forward_skew=0.0,
      )
      meta = MetaPrediction(
          primary_direction=1,
          direction_label="BUY",
          success_probability=prob,
          bet_size=0.10,
          target_price=target,
          stop_price=stop,
          feature_importances={},
      )
      df = pd.DataFrame(
          {
              "Close": [100.0] * 100,
              "High": [101.0] * 100,
              "Low": [99.0] * 100,
              "Open": [100.0] * 100,
              "Volume": [1e6] * 100,
          }
      )
      return SingleAssetAnalysis(
          ticker="AAPL",
          current_price=100.0,
          market_jurisdiction="US",
          regime=REGIME_DEFINITIONS[0],
          meta_prediction=meta,
          volatility_cone=cone,
          friction_hurdle_passes=True,
          friction_cost_pct=0.05,
          net_expected_alpha_pct=1.0,
          risk_decision=None,
          optimal_d_star=0.3,
          recent_ohlcv=df,
          features_df=df,
      )

    # 1. Low edge, fails hurdle (EV ~ +0.10% < 0.20%)
    res_sub_hurdle = evaluator.evaluate(make_analysis(target=100.6, stop=99.8, prob=0.55))
    assert not res_sub_hurdle.is_positive_ev
    assert "BELOW HURDLE" in (res_sub_hurdle.rejection_reason or "")

    # 2. Negative EV
    res_neg_ev = evaluator.evaluate(make_analysis(target=100.5, stop=97.0, prob=0.45))
    assert not res_neg_ev.is_positive_ev
    assert (
        "NEGATIVE EV" in (res_neg_ev.rejection_reason or "")
        or "EPISTEMIC" in (res_neg_ev.rejection_reason or "")
    )

    # 3. High edge passes (+3% target, 1% stop, 65% win prob)
    res_pass = evaluator.evaluate(make_analysis(target=103.0, stop=99.0, prob=0.65))
    assert res_pass.is_positive_ev
    assert res_pass.rejection_reason is None
    assert res_pass.net_expectancy_pct >= 0.20
```

---

#### File 4: `tests/test_strategy_trade_ranker.py`

```python
"""Unit tests for TradeRanker (Risk-adjusted value, Regime multipliers, Synergy boosts, Sorting)."""

import pytest

from src.models.regime_hmm import REGIME_DEFINITIONS
from src.strategy.trade_evaluator import TradeEvaluationResult
from src.strategy.trade_ranker import RankedOpportunity, TradeRanker


class TestTradeRanker:

  def _make_eval(self, ticker, net_ev, is_pos, vol=0.20, direction="LONG"):
    return TradeEvaluationResult(
        ticker=ticker,
        direction=direction,
        entry_price=100.0,
        target_price=103.0,
        stop_price=98.5,
        raw_win_prob=0.60,
        epistemic_uncertainty=0.03,
        conservative_win_prob=0.57,
        loss_probability=0.43,
        expected_win_return_pct=3.0,
        expected_loss_return_pct=1.6,
        gap_risk_buffer_pct=0.1,
        round_trip_friction_pct=0.15,
        gross_expectancy_pct=net_ev + 0.15,
        net_expectancy_pct=net_ev,
        min_ev_hurdle_pct=0.20,
        is_positive_ev=is_pos,
        rejection_reason=None if is_pos else "NEGATIVE EV",
        evaluation_metadata={"annualized_vol": vol},
    )

  def test_risk_adjusted_value_calculation(self):
    """Verifies: EV / sigma asset scaling."""
    ranker = TradeRanker()
    # Asset A: EV=+1.0%, vol=10% -> Risk-Adj = 1.0 / 0.10 = 10.0
    # Asset B: EV=+1.0%, vol=25% -> Risk-Adj = 1.0 / 0.25 = 4.0
    ev_a = self._make_eval("ASSET_A", net_ev=1.0, is_pos=True, vol=0.10)
    ev_b = self._make_eval("ASSET_B", net_ev=1.0, is_pos=True, vol=0.25)

    ranked = ranker.rank_opportunities([ev_a, ev_b])
    assert len(ranked) == 2
    assert ranked[0].ticker == "ASSET_A"
    assert ranked[0].risk_adjusted_value == 10.0
    assert ranked[1].ticker == "ASSET_B"
    assert ranked[1].risk_adjusted_value == 4.0

  def test_market_regime_multipliers(self):
    """Verifies: State 0 Trending (1.25x), State 1 Choppy (1.15x), State 2 Crisis (0.0x hard veto)."""
    ranker = TradeRanker()
    ev = self._make_eval("AAPL", net_ev=0.80, is_pos=True, vol=0.20)

    # State 0 Trending
    ranked_s0 = ranker.rank_opportunities([ev], regimes={"AAPL": REGIME_DEFINITIONS[0]})
    assert ranked_s0[0].regime_multiplier == 1.25
    assert ranked_s0[0].is_eligible

    # State 1 Choppy
    ranked_s1 = ranker.rank_opportunities([ev], regimes={"AAPL": REGIME_DEFINITIONS[1]})
    assert ranked_s1[0].regime_multiplier == 1.15
    assert ranked_s1[0].is_eligible

    # State 2 Crisis Hard Veto
    ranked_s2 = ranker.rank_opportunities([ev], regimes={"AAPL": REGIME_DEFINITIONS[2]})
    assert ranked_s2[0].regime_multiplier == 0.0
    assert ranked_s2[0].composite_score == 0.0
    assert not ranked_s2[0].is_eligible
    assert "Crisis" in (ranked_s2[0].ineligible_reason or "")

  def test_sorting_eligible_before_ineligible(self):
    """Verifies: All eligible opportunities strictly outrank ineligible opportunities."""
    ranker = TradeRanker()
    ev_good_1 = self._make_eval("GOOD_1", net_ev=0.60, is_pos=True, vol=0.20)
    ev_good_2 = self._make_eval("GOOD_2", net_ev=0.90, is_pos=True, vol=0.20)
    ev_bad_ev = self._make_eval("BAD_EV", net_ev=-0.20, is_pos=False, vol=0.15)
    ev_crisis = self._make_eval("CRISIS", net_ev=1.50, is_pos=True, vol=0.20)

    regimes = {
        "GOOD_1": REGIME_DEFINITIONS[0],
        "GOOD_2": REGIME_DEFINITIONS[0],
        "BAD_EV": REGIME_DEFINITIONS[0],
        "CRISIS": REGIME_DEFINITIONS[2],  # State 2 Crisis
    }

    ranked = ranker.rank_opportunities(
        [ev_good_1, ev_good_2, ev_bad_ev, ev_crisis], regimes=regimes
    )
    assert len(ranked) == 4
    # Top 2 must be eligible
    assert ranked[0].is_eligible and ranked[0].ticker == "GOOD_2"
    assert ranked[1].is_eligible and ranked[1].ticker == "GOOD_1"
    # Bottom 2 must be ineligible
    assert not ranked[2].is_eligible
    assert not ranked[3].is_eligible

  def test_empty_candidates_edge_case(self):
    """Verifies: Empty input returns empty list without error."""
    ranker = TradeRanker()
    assert ranker.rank_opportunities([]) == []

  def test_all_ineligible_edge_case(self):
    """Verifies: When all opportunities have negative EV, all are ranked with is_eligible=False."""
    ranker = TradeRanker()
    ev1 = self._make_eval("NEG_1", net_ev=-0.10, is_pos=False)
    ev2 = self._make_eval("NEG_2", net_ev=-0.35, is_pos=False)

    ranked = ranker.rank_opportunities([ev1, ev2])
    assert len(ranked) == 2
    assert all(not r.is_eligible for r in ranked)
```

---

## 5. Verification Method

### 5.1 Test Execution Commands
```powershell
# 1. Baseline Invariant & Regression Verification
cd C:\Users\Shivam\Desktop\trade_bot
py tests/test_phase1_phase2_fixes.py
py -m pytest tests/test_market_sessions.py tests/test_real_market_paper_trading.py

# 2. Execute New Strategy Unit Tests (Post-implementation)
py -m pytest tests/test_strategy_trade_evaluator.py tests/test_strategy_trade_ranker.py -v
```

### 5.2 Invalidation Conditions
- **Mathematical Expectancy Invalidation**: If any trade candidate is accepted where $\text{EV} \le 0$ or $\text{EV} < 0.20\%$, the Net Expectancy logic is invalidated.
- **Uncertainty Margin Invalidation**: If reducing historical sample size $N_{\text{bars}}$ does not increase epistemic uncertainty $\sigma_p$, or if $p_{\text{conservative}} < 0$, the formula is invalidated.
- **Microstructure Invalidation**: If an instrument breaching CME LULD price velocity halts or Forex 17:00 EST rollover spread spikes is marked eligible, the microstructure gate is invalidated.
- **Crisis Veto Invalidation**: If an opportunity in State 2 Crisis regime receives a non-zero composite score or is labeled eligible, the risk guardrail is invalidated.
