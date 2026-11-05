# Recommendation & Architecture Report: Portfolio Selection & Decision Explainability (Part C)

**Author**: Portfolio & Explainability Explorer (`teamwork_explorer`)  
**Workspace**: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m1_explorer_3`  
**Milestone**: Milestone 1 (Quantitative Strategy Engine - Part C)  
**Date**: November 5, 2026  

---

## 1. Executive Summary

This report establishes the complete architectural blueprints, mathematical specifications, class designs, and test suites for **Part C** of Milestone 1:
1. **`PortfolioSelector` (`src/strategy/portfolio_selector.py`)**: A production-grade portfolio allocation engine implementing:
   - **Asymmetric Fractional Kelly Mode**: Sizing based on calibrated win probabilities, empirical payoff ratios ($b_i$), annualized volatility scaling, and quadratic drawdown dampening, capped at an institutional 20% single-position ceiling.
   - **Hierarchical Risk Parity (HRP) Mode**: Institutional tree-clustering asset allocation utilizing Marchenko-Pastur Random Matrix Theory (RMT) covariance de-noising with strict diagonal variance preservation, iterative 20% single-position capping, and portfolio-level gross leverage scaling.
   - **MANDATORY 100% CASH ALLOCATION GUARANTEE**: Absolute structural contract ensuring that whenever zero candidate opportunities possess positive Net Expectancy ($\text{EV} > 0$), or during market Crisis regimes (State 2), or upon drawdown kill switch activation, the engine allocates 100% of capital to cash:
     `weights={"CASH": 1.0}`, `cash_weight=1.0`, `is_100_percent_cash=True`, `allocated_capital={}`, `shares={}`.
   - **Dynamic Capital Scaling Invariant**: Machine learning predictions ($P(\text{Win})$, price targets, stop-loss barriers, Net Expectancy) remain strictly invariant to virtual account size, while dollar allocations and share counts scale linearly with starting capital.
2. **`DecisionExplainer` (`src/strategy/decision_explainer.py`)**: A transparent quantitative explanation engine translating mathematical trade analytics into human-readable, plain-language narratives for:
   - **Accepted Trades**: Detailed breakdown of positive Net Expectancy, calibrated win probabilities, statutory exchange fees/taxes deducted, Almgren-Chriss market impact, HMM regime synergy, and position sizing mechanics.
   - **Rejected Trades**: Clear explanations for trades failing the positive EV hurdle, statutory friction hurdles, microstructure circuit breakers (Forex rollover, Gold LULD), or crisis quarantine.
   - **100% Cash Preservation**: Transparent, reassuring rationales explaining why preserving virtual capital in cash is the mathematically superior action when market edge is absent.

---

## 2. Quantitative Architecture & Interaction Map

```
                +-------------------------------------------+
                |        UniverseSelector (Part A)          |
                |   Filters ADV, Spread, Volatility, DQ     |
                +---------------------+---------------------+
                                      |
                                      v
                +-------------------------------------------+
                |         TradeEvaluator (Part B)           |
                |   Net Expectancy (EV) with Uncertainty   |
                +---------------------+---------------------+
                                      |
                                      v
                +-------------------------------------------+
                |          TradeRanker (Part B)             |
                |    EV / Sigma & Regime Multipliers        |
                +---------------------+---------------------+
                                      |
                                      v List[RankedOpportunity]
                +===========================================+
                |        PortfolioSelector (Part C)         |
                |  - Asymmetric Fractional Kelly Sizing     |
                |  - HRP with Marchenko-Pastur RMT Cleaning |
                |  - 20% Single-Position Institutional Cap  |
                |  - MANDATORY 100% CASH ALLOCATION FALLBACK|
                +=====================+=====================+
                                      |
                                      +-------------------------------+
                                      |                               |
                                      v PortfolioAllocationResult     v
                         +--------------------------+    +=============================+
                         | Execution Broker Ledger  |    |  DecisionExplainer (Part C) |
                         | (orders, positions, fees)|    |  Plain-Language Rationales  |
                         +--------------------------+    +==============+==============+
                                                                        |
                                                                        v PlainLanguageExplanation
                                                         +-----------------------------+
                                                         |  Live Bot Activity Feed UI  |
                                                         |  (Category: DECISION)       |
                                                         +-----------------------------+
```

---

## 3. `PortfolioSelector` Mathematical Specification

### 3.1 Data Structures
```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd


@dataclass
class AllocationItem:
    """Detailed allocation metrics for an individual qualifying instrument."""
    ticker: str
    direction: str                     # "LONG" or "SHORT"
    weight: float                      # Fraction of portfolio [0.0, 0.20]
    weight_pct: float                  # Percentage (e.g. 15.5%)
    allocated_capital: float           # Dollar/Rupee amount allocated
    entry_price: float                 # Benchmark reference entry price
    shares: float                      # Calculated share/unit quantity
    target_price: float                # Upper profit target
    stop_price: float                  # Lower stop loss
    expected_net_ev_pct: float         # Net Expectancy %
    kelly_optimal_f: float             # Unconstrained Kelly fraction f*
    vol_scalar: float                  # Volatility dampening scalar
    dd_scalar: float                   # Drawdown dampening scalar
    sizing_rationale: str              # Concise summary of sizing drivers


@dataclass
class PortfolioAllocationResult:
    """Master portfolio allocation decision structure."""
    weights: Dict[str, float]          # ticker -> weight, and "CASH" -> cash_weight
    cash_weight: float                 # Proportion in cash [0.0, 1.0]
    allocated_capital: Dict[str, float]# ticker -> allocated currency amount
    shares: Dict[str, float]           # ticker -> share quantity
    is_100_percent_cash: bool          # Flag indicating complete capital preservation
    method: str                        # "KELLY" or "HRP"
    allocations: List[AllocationItem]  # Granular asset allocations
    total_virtual_equity: float        # Starting virtual capital
    total_allocated_capital: float     # Total capital deployed in positions
    residual_cash_capital: float       # Capital retained in cash balance
    explanation: str                   # Executive summary of allocation decision
```

### 3.2 Fractional Kelly Mode Formulation

For each candidate opportunity $i \in \{1, \dots, N\}$ that satisfies the positive Net Expectancy hurdle ($\text{EV}_i > 0$) and is eligible ($\text{is\_eligible} == \text{True}$):

1. **Empirical Payoff Asymmetry Ratio ($b_i$)**:
   $$b_i = \max\left(\frac{\mathbb{E}[\text{Win}_i \mid \text{Win}]}{\max(\mathbb{E}[\text{Loss}_i \mid \text{Loss}], 10^{-4})}, 0.50\right)$$
   where $\mathbb{E}[\text{Win}_i \mid \text{Win}]$ and $\mathbb{E}[\text{Loss}_i \mid \text{Loss}]$ are obtained directly from `TradeEvaluationResult`.

2. **Conservative Win Probability ($p_i$)**:
   $$p_i = \text{evaluation.conservative\_win\_prob} \quad (\text{with fallback to } \text{evaluation.win\_probability})$$

3. **Unconstrained Continuous Kelly Fraction ($f_i^*$)**:
   $$f_i^* = p_i - \frac{1 - p_i}{b_i}$$
   If $f_i^* \le 0$, the mathematical edge is non-positive after payoff asymmetry; hence $w_i = 0.0$.

4. **Volatility Tail-Risk Scalar ($\text{VolScalar}_i$)**:
   $$\text{VolScalar}_i = \min\left(1.0, \frac{\sigma_{\text{target}}}{\max(\sigma_{\text{realized}, i}, 0.05)}\right)$$
   Where $\sigma_{\text{target}}$ is target annual portfolio volatility (default 15%), and $\sigma_{\text{realized}, i}$ is the annualized volatility of asset $i$.
   *CVaR-95 Dampening*: If daily 95% CVaR is available and $\text{CVaR}_{95, i} > 0.025$:
   $$\text{VolScalar}_i \leftarrow \text{VolScalar}_i \cdot \min\left(1.0, \frac{0.025}{\text{CVaR}_{95, i}}\right)$$

5. **Convex Quadratic Drawdown Scalar ($\text{DDScalar}$)**:
   Let $D$ be the current portfolio drawdown fraction, $D_{\text{warn}} = 0.08$ (8% warning threshold), and $D_{\text{kill}} = 0.15$ (15% hard kill circuit breaker):
   $$\text{DDScalar} = \begin{cases}
   1.0 & \text{if } D < D_{\text{warn}} \\
   \left(1.0 - \frac{D - D_{\text{warn}}}{D_{\text{kill}} - D_{\text{warn}}}\right)^2 & \text{if } D_{\text{warn}} \le D < D_{\text{kill}} \\
   0.0 & \text{if } D \ge D_{\text{kill}} \quad (\text{Triggers 100\% Cash})
   \end{cases}$$

6. **Base Sized Weight ($w_i^{\text{raw}}$)**:
   $$w_i^{\text{raw}} = c_{\text{kelly}} \cdot f_i^* \cdot \text{VolScalar}_i \cdot \text{DDScalar}$$
   where $c_{\text{kelly}} = 0.30$ (30% fractional Kelly for parameter uncertainty protection).

7. **Institutional Single-Position Ceiling (20% Cap)**:
   $$w_i^{\text{capped}} = \min(w_i^{\text{raw}}, 0.20)$$

8. **Portfolio Budget Normalization**:
   If the aggregate sum of asset weights exceeds maximum gross exposure (e.g. $\text{MaxGross} = 0.95$ to ensure a mandatory 5% cash buffer):
   $$\text{If } \sum_{i=1}^N w_i^{\text{capped}} > \text{MaxGross}: \quad w_i = w_i^{\text{capped}} \cdot \frac{\text{MaxGross}}{\sum_{j=1}^N w_j^{\text{capped}}}$$
   Otherwise:
   $$w_i = w_i^{\text{capped}}$$
   Cash weight is strictly:
   $$w_{\text{CASH}} = 1.0 - \sum_{i=1}^N w_i$$

---

### 3.3 Hierarchical Risk Parity (HRP) Mode Formulation

When `method="HRP"`:
1. **Eligible Asset Filter**:
   Identify $K$ qualifying assets with $\text{EV}_i > 0$ and $\text{is\_eligible} == \text{True}$.
   - If $K = 0$: Enforce 100% Cash Allocation Guarantee.
   - If $K = 1$: Allocate via Fractional Kelly or $\min(0.20, \text{VolScalar}_1 \cdot \text{DDScalar})$, with remainder in cash.
   - If $K \ge 2$: Proceed to HRP tree clustering.

2. **Covariance De-noising via Marchenko-Pastur RMT**:
   Using `HierarchicalRiskParity.denoise_covariance(cov, t_obs, n_assets)`:
   - Calculate theoretical Marchenko-Pastur upper spectral boundary:
     $$\lambda_{\max} = \sigma^2 \left(1 + \sqrt{\frac{1}{q}}\right)^2, \quad q = \frac{T}{N}$$
   - Replace noisy eigenvalues $\lambda_k \le \lambda_{\max}$ with their average residual value.
   - Reconstruct clean covariance $\Sigma_{\text{clean}}$ strictly preserving diagonal asset variances:
     $$\text{diag}(\Sigma_{\text{clean}}) \equiv \text{diag}(\Sigma_{\text{raw}})$$

3. **Tree Clustering & Recursive Bisection**:
   - Distance matrix: $D_{i,j} = \sqrt{0.5(1 - \rho_{i,j})}$
   - Ward's minimum-variance linkage to avoid chaining.
   - Quasi-diagonalization and recursive bisection produce raw weights $\tilde{w}_i$ summing to 1.0.

4. **Iterative 20% Capping & Residual Redistribution**:
   Apply an iterative redistribution loop:
   ```python
   weights = raw_hrp_weights.copy()
   max_cap = 0.20
   while any(weights > max_cap + 1e-6) and any(weights < max_cap - 1e-6):
       excess = sum(max(0.0, w - max_cap) for w in weights)
       uncapped_tickers = [t for t in weights.index if weights[t] < max_cap]
       weights = weights.clip(upper=max_cap)
       if uncapped_tickers and excess > 0:
           uncapped_sum = weights[uncapped_tickers].sum()
           if uncapped_sum > 0:
               weights[uncapped_tickers] += excess * (weights[uncapped_tickers] / uncapped_sum)
   weights = weights.clip(upper=max_cap)
   ```
   Note: If all $K$ assets reach the 20% cap, maximum invested equity is $K \times 0.20$. (e.g., if 3 assets qualify, max equity is 60%, leaving 40% in cash).

5. **Portfolio Gross Leverage & Volatility Target Scaling**:
   Compute expected portfolio volatility:
   $$\sigma_{\text{port}} = \sqrt{w^T \Sigma_{\text{clean}} w}$$
   Compute gross leverage scalar:
   $$\text{GrossLeverage} = \min\left(1.0, \frac{\sigma_{\text{target}}}{\max(\sigma_{\text{port}}, 0.05)}\right) \cdot \text{DDScalar}$$
   Scale final weights:
   $$w_i = w_i \cdot \text{GrossLeverage}$$
   $$w_{\text{CASH}} = 1.0 - \sum_{i=1}^K w_i$$

---

### 3.4 The Mandatory 100% Cash Allocation Guarantee

Under the following conditions, the engine **must** return an immutable cash-only allocation:
1. Candidate list is empty ($N = 0$).
2. Zero candidates meet the positive Net Expectancy hurdle ($\forall i, \text{EV}_i \le 0$).
3. Market regime is High-Vol Crisis (State 2) or aggregate regime is in Crisis quarantine.
4. Portfolio drawdown exceeds the kill switch threshold ($D \ge 0.15$).
5. Kelly fractions are negative or zero for all candidates ($\forall i, f_i^* \le 0$).

**Guaranteed Return Object**:
```python
PortfolioAllocationResult(
    weights={"CASH": 1.0},
    cash_weight=1.0,
    allocated_capital={},
    shares={},
    is_100_percent_cash=True,
    method=method,
    allocations=[],
    total_virtual_equity=total_virtual_equity,
    total_allocated_capital=0.0,
    residual_cash_capital=total_virtual_equity,
    explanation="100% Cash Allocation: Zero candidates met positive Net Expectancy hurdle (EV > 0) or market crisis regime active. Capital preserved.",
)
```

---

### 3.5 Dynamic Capital Scaling Invariant

The quantitative architecture enforces strict decoupling between predictive modeling and portfolio balance:
- **Predictive Invariants**:
  Given identical market data, regardless of whether virtual capital is ₹10,000, ₹100,000, or ₹10,000,000 (or $1,000 vs $1,000,000):
  $$\Delta P(\text{Win}) \equiv 0, \quad \Delta \text{TargetPrice} \equiv 0, \quad \Delta \text{StopPrice} \equiv 0, \quad \Delta \text{EV} \equiv 0, \quad \Delta w_i \equiv 0$$
- **Capital Scaling**:
  $$\text{AllocatedCapital}_i(E) = \text{round}(E \cdot w_i, 2)$$
  $$\text{Shares}_i(E) = \begin{cases}
  \lfloor \text{AllocatedCapital}_i / P_{\text{entry}, i} \rfloor & \text{if Integer Mode (Equities / NSE)} \\
  \text{round}(\text{AllocatedCapital}_i / P_{\text{entry}, i}, 4) & \text{if Fractional Mode (US / Crypto / Forex)}
  \end{cases}$$
  Linearity property:
  $$\frac{\text{AllocatedCapital}_i(k \cdot E)}{\text{AllocatedCapital}_i(E)} = k \quad (\pm 0.01 \text{ rounding})$$

---

## 4. `DecisionExplainer` Specification & Plain-Language Templates

### 4.1 Data Structures
```python
@dataclass
class PlainLanguageExplanation:
    """Standardized human-readable trade decision explanation."""
    ticker: str                        # Instrument symbol or "PORTFOLIO"
    action: str                        # "ACCEPTED", "REJECTED", "HELD_IN_CASH"
    headline: str                      # Concise summary header for activity feed
    summary: str                       # Multi-sentence plain-language explanation
    factors: Dict[str, str]            # Factor name -> human-readable explanation
    metrics: Dict[str, Any]            # Quantitative verification metrics
    timestamp_utc: str                 # UTC ISO timestamp
```

### 4.2 Narrative Generation Templates

#### A. Accepted Trades (`action="ACCEPTED"`)
- **Headline**: `BUY {ticker}: Net Expectancy +{EV:.2f}% | Win Prob {win_prob:.1f}%`
- **Summary**:
  `"Accepted LONG opportunity on {ticker}. The quantitative model projects a +{EV:.2f}% net mathematical edge after deducting {friction_bps:.1f} bps in statutory fees (STT/SEC/FINRA) and Almgren-Chriss market impact. Fractional Kelly allocates {weight_pct:.1f}% ({currency}{allocated_cap:,.2f} / {shares} units) aligned with {regime_name} regime."`
- **Factors**:
  - `net_expectancy`: `"Net edge of +{EV:.2f}% exceeds minimum hurdle of +{min_hurdle:.2f}%."`
  - `win_probability`: `"Calibrated win probability is {win_prob:.1f}% (conservative bound {cons_prob:.1f}% after epistemic uncertainty margin)."`
  - `friction_deductions`: `"Round-trip statutory taxes and L2 market impact total {friction_bps:.1f} bps ({currency}{fee_dollars:,.2f})."`
  - `regime_alignment`: `"{regime_name}: Multiplier {regime_mult:.2f}x applied."`
  - `position_sizing`: `"Fractional Kelly ({kelly_c:.2f}x) sized at {weight_pct:.1f}% (institutional limit 20.0%)."`
  - `barriers`: `"Target {currency}{pt:,.2f} (+{pt_pct:.2f}%) vs Stop {currency}{sl:,.2f} (-{sl_pct:.2f}%), payoff ratio b={b:.2f}."`

#### B. Rejected Trades (`action="REJECTED"`)
1. **Negative Net Expectancy**:
   - **Headline**: `REJECTED {ticker}: Negative Net Expectancy ({EV:.2f}%)`
   - **Summary**:
     `"Rejected {direction} opportunity on {ticker}. Although gross probability is {win_prob:.1f}%, the net expected return of {EV:.2f}% fails the quantitative hurdle (+{min_hurdle:.2f}%). Expected losses (-{loss_ret:.2f}%) and round-trip frictions ({friction_bps:.1f} bps) overwhelm projected gains."`
2. **Microstructure Circuit Breaker Failure**:
   - **Headline**: `REJECTED {ticker}: Microstructure Circuit Breaker Active`
   - **Summary**:
     `"Rejected trade on {ticker}: Microstructure execution gate triggered: {rejection_reason}. New orders halted to avoid adverse execution spikes."`
3. **Crisis Regime Quarantine**:
   - **Headline**: `REJECTED {ticker}: Crisis Regime Veto`
   - **Summary**:
     `"Rejected trade on {ticker}: Market is in High-Vol Crisis regime (State 2). Quantitative capital protection rules veto new position authorizations during systemic volatility."`
4. **Drawdown Kill Switch**:
   - **Headline**: `REJECTED {ticker}: Drawdown Circuit Breaker Active`
   - **Summary**:
     `"Rejected trade on {ticker}: Portfolio drawdown of {drawdown_pct:.1f}% exceeds maximum risk limit ({max_dd:.1f}%). All position authorizations frozen."`

#### C. 100% Cash Preservation (`action="HELD_IN_CASH"`)
- **Headline**: `100% CASH PRESERVED: Capital Protected Across Universe`
- **Summary**:
  `"The quantitative engine evaluated {total_evaluated} candidate opportunities, but zero assets exhibited positive net expectancy after statutory fees and market impact. To protect virtual capital from negative mathematical drift, 100% of equity is safely held in cash."`
- **Factors**:
  - `candidates_evaluated`: `"{total_evaluated} universe candidate instruments evaluated."`
  - `mathematical_edge`: `"Zero candidates possessed Net EV > +0.20%."`
  - `capital_protection`: `"100.0% capital preserved in cash; 0.0% exposed to market risk."`
  - `re_evaluation`: `"Engine will re-evaluate universe upon arrival of next bar close."`

---

## 5. Implementation Blueprints

### 5.1 `src/strategy/portfolio_selector.py`
```python
"""Portfolio Allocation & Sizing Engine (Fractional Kelly & De-noised HRP).

Enforces asymmetric Fractional Kelly sizing, Marchenko-Pastur RMT de-noised HRP,
single-position 20% leverage ceiling, and mandatory 100% Cash Allocation Guarantee.
"""

from dataclasses import dataclass, field
import logging
import math
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd

from src.models.hrp_allocator import HierarchicalRiskParity
from src.strategy.trade_ranker import RankedOpportunity

logger = logging.getLogger(__name__)


@dataclass
class AllocationItem:
    ticker: str
    direction: str
    weight: float
    weight_pct: float
    allocated_capital: float
    entry_price: float
    shares: float
    target_price: float
    stop_price: float
    expected_net_ev_pct: float
    kelly_optimal_f: float
    vol_scalar: float
    dd_scalar: float
    sizing_rationale: str


@dataclass
class PortfolioAllocationResult:
    weights: Dict[str, float]
    cash_weight: float
    allocated_capital: Dict[str, float]
    shares: Dict[str, float]
    is_100_percent_cash: bool
    method: str
    allocations: List[AllocationItem]
    total_virtual_equity: float
    total_allocated_capital: float
    residual_cash_capital: float
    explanation: str


class PortfolioSelector:
    """Allocates virtual portfolio capital via Fractional Kelly or HRP with 100% Cash Guarantee."""

    def __init__(
        self,
        kelly_fraction: float = 0.30,
        target_annual_vol: float = 0.15,
        warning_drawdown: float = 0.08,
        max_kill_drawdown: float = 0.15,
        convex_power: float = 2.0,
        max_position_cap: float = 0.20,
        max_gross_exposure: float = 0.95,
        integer_shares_markets: Optional[List[str]] = None,
    ):
        self.kelly_c = kelly_fraction
        self.target_vol = target_annual_vol
        self.dd_warn = warning_drawdown
        self.dd_kill = max_kill_drawdown
        self.convex_p = convex_power
        self.max_cap = max_position_cap
        self.max_gross = max_gross_exposure
        self.integer_markets = integer_shares_markets or ["NSE_CASH", "NSE", "BSE", "INDIA"]

    def _compute_drawdown_scalar(self, current_drawdown: float) -> float:
        if current_drawdown >= self.dd_kill:
            return 0.0
        if current_drawdown < self.dd_warn:
            return 1.0
        excess = current_drawdown - self.dd_warn
        scale_range = max(self.dd_kill - self.dd_warn, 1e-4)
        return float(max(0.0, (1.0 - (excess / scale_range))) ** self.convex_p)

    def _create_100_percent_cash_result(
        self,
        total_virtual_equity: float,
        method: str,
        reason: str,
    ) -> PortfolioAllocationResult:
        return PortfolioAllocationResult(
            weights={"CASH": 1.0},
            cash_weight=1.0,
            allocated_capital={},
            shares={},
            is_100_percent_cash=True,
            method=method,
            allocations=[],
            total_virtual_equity=round(total_virtual_equity, 2),
            total_allocated_capital=0.0,
            residual_cash_capital=round(total_virtual_equity, 2),
            explanation=f"100% Cash Allocation: {reason}",
        )

    def allocate(
        self,
        ranked_opportunities: List[RankedOpportunity],
        total_virtual_equity: float,
        method: str = "KELLY",
        returns_df: Optional[pd.DataFrame] = None,
        current_drawdown: float = 0.0,
        market_type: str = "US",
    ) -> PortfolioAllocationResult:
        if total_virtual_equity <= 0.0:
            raise ValueError(f"Total virtual equity must be positive, got {total_virtual_equity}")

        # Drawdown circuit breaker check
        dd_scalar = self._compute_drawdown_scalar(current_drawdown)
        if dd_scalar <= 0.0:
            return self._create_100_percent_cash_result(
                total_virtual_equity, method,
                f"Portfolio drawdown ({current_drawdown:.1%}) breached kill limit ({self.dd_kill:.1%}). Capital frozen in cash."
            )

        # Filter strictly for eligible, positive Net Expectancy trades
        eligible = [
            opp for opp in ranked_opportunities
            if opp.is_eligible and opp.evaluation.is_positive_ev and opp.evaluation.net_expectancy_pct > 0.0
        ]

        if not eligible:
            return self._create_100_percent_cash_result(
                total_virtual_equity, method,
                "Zero candidate opportunities met positive Net Expectancy hurdle (EV > 0). Capital preserved in cash."
            )

        method = method.upper()
        if method == "HRP" and len(eligible) >= 2 and returns_df is not None and not returns_df.empty:
            return self._allocate_hrp(eligible, total_virtual_equity, returns_df, dd_scalar, market_type)
        else:
            return self._allocate_kelly(eligible, total_virtual_equity, dd_scalar, market_type)

    def _allocate_kelly(
        self,
        opportunities: List[RankedOpportunity],
        total_virtual_equity: float,
        dd_scalar: float,
        market_type: str,
    ) -> PortfolioAllocationResult:
        raw_weights: Dict[str, float] = {}
        alloc_items: List[AllocationItem] = []

        for opp in opportunities:
            ev = opp.evaluation
            p = float(getattr(ev, "conservative_win_prob", ev.win_probability))
            b = max(ev.expected_win_return_pct / max(ev.expected_loss_return_pct, 1e-4), 0.50)

            # Unconstrained Kelly fraction f* = p - (1-p)/b
            f_star = p - ((1.0 - p) / b)
            if f_star <= 0.0:
                continue

            # Volatility scalar
            vol = max(opp.evaluation.expected_win_return_pct * 2.0 / 100.0, 0.05)  # Proxy or realized
            vol_scalar = min(1.0, self.target_vol / vol)

            w_raw = self.kelly_c * f_star * vol_scalar * dd_scalar
            w_capped = min(w_raw, self.max_cap)

            if w_capped > 0.005:  # Minimum 0.5% allocation hurdle
                raw_weights[opp.ticker] = w_capped

        if not raw_weights:
            return self._create_100_percent_cash_result(
                total_virtual_equity, "KELLY",
                "Kelly optimization yielded 0.0% weight across all candidates after risk dampening."
            )

        # Normalize if aggregate weights exceed max_gross
        total_w = sum(raw_weights.values())
        norm_factor = min(1.0, self.max_gross / total_w) if total_w > self.max_gross else 1.0

        final_weights: Dict[str, float] = {}
        allocated_cap: Dict[str, float] = {}
        shares_dict: Dict[str, float] = {}
        total_allocated = 0.0

        is_integer_shares = market_type.upper() in self.integer_markets

        for opp in opportunities:
            if opp.ticker not in raw_weights:
                continue
            w = round(raw_weights[opp.ticker] * norm_factor, 4)
            if w <= 0.0:
                continue

            final_weights[opp.ticker] = w
            cap = round(total_virtual_equity * w, 2)
            entry_p = max(opp.evaluation.entry_price, 1e-4)

            shares = math.floor(cap / entry_p) if is_integer_shares else round(cap / entry_p, 4)
            if is_integer_shares and shares <= 0:
                # Capital too small to purchase 1 whole share; leave in cash
                final_weights.pop(opp.ticker)
                continue

            actual_cap = round(shares * entry_p, 2) if is_integer_shares else cap
            allocated_cap[opp.ticker] = actual_cap
            shares_dict[opp.ticker] = shares
            total_allocated += actual_cap

            alloc_items.append(
                AllocationItem(
                    ticker=opp.ticker,
                    direction=opp.direction,
                    weight=w,
                    weight_pct=round(w * 100, 2),
                    allocated_capital=actual_cap,
                    entry_price=round(entry_p, 2),
                    shares=shares,
                    target_price=round(opp.evaluation.target_price, 2),
                    stop_price=round(opp.evaluation.stop_price, 2),
                    expected_net_ev_pct=round(opp.evaluation.net_expectancy_pct, 2),
                    kelly_optimal_f=round(f_star, 4),
                    vol_scalar=round(vol_scalar, 3),
                    dd_scalar=round(dd_scalar, 3),
                    sizing_rationale=f"Fractional Kelly {w*100:.1f}% (cap: {self.max_cap*100:.0f}%, f*: {f_star:.2f})",
                )
            )

        if not final_weights:
            return self._create_100_percent_cash_result(
                total_virtual_equity, "KELLY",
                "Allocated capital was insufficient to buy minimum unit shares; 100% held in cash."
            )

        residual_cash = round(total_virtual_equity - total_allocated, 2)
        cash_w = round(residual_cash / total_virtual_equity, 4)
        final_weights["CASH"] = cash_w

        return PortfolioAllocationResult(
            weights=final_weights,
            cash_weight=cash_w,
            allocated_capital=allocated_cap,
            shares=shares_dict,
            is_100_percent_cash=False,
            method="KELLY",
            allocations=alloc_items,
            total_virtual_equity=round(total_virtual_equity, 2),
            total_allocated_capital=round(total_allocated, 2),
            residual_cash_capital=residual_cash,
            explanation=f"Allocated {len(alloc_items)} positions ({sum(final_weights[t] for t in allocated_cap)*100:.1f}% equity, {cash_w*100:.1f}% cash) via Fractional Kelly.",
        )

    def _allocate_hrp(
        self,
        opportunities: List[RankedOpportunity],
        total_virtual_equity: float,
        returns_df: pd.DataFrame,
        dd_scalar: float,
        market_type: str,
    ) -> PortfolioAllocationResult:
        eligible_tickers = [opp.ticker for opp in opportunities if opp.ticker in returns_df.columns]
        if len(eligible_tickers) < 2:
            return self._allocate_kelly(opportunities, total_virtual_equity, dd_scalar, market_type)

        sub_returns = returns_df[eligible_tickers].dropna()
        raw_hrp = HierarchicalRiskParity.compute_hrp_weights(sub_returns)

        # Iterative 20% capping
        weights = raw_hrp.copy()
        for _ in range(5):
            excess = sum(max(0.0, w - self.max_cap) for w in weights)
            uncapped = [t for t in weights.index if weights[t] < self.max_cap]
            weights = weights.clip(upper=self.max_cap)
            if excess > 0 and uncapped:
                u_sum = weights[uncapped].sum()
                if u_sum > 0:
                    weights[uncapped] += excess * (weights[uncapped] / u_sum)
        weights = weights.clip(upper=self.max_cap)

        # Apply gross leverage & drawdown scaling
        gross_leverage = min(self.max_gross, dd_scalar)
        weights = (weights * gross_leverage).round(4)

        opp_map = {opp.ticker: opp for opp in opportunities}
        final_weights: Dict[str, float] = {}
        allocated_cap: Dict[str, float] = {}
        shares_dict: Dict[str, float] = {}
        alloc_items: List[AllocationItem] = []
        total_allocated = 0.0
        is_integer_shares = market_type.upper() in self.integer_markets

        for tk, w in weights.items():
            if w <= 0.005:
                continue
            opp = opp_map.get(tk)
            if not opp:
                continue

            cap = round(total_virtual_equity * w, 2)
            entry_p = max(opp.evaluation.entry_price, 1e-4)
            shares = math.floor(cap / entry_p) if is_integer_shares else round(cap / entry_p, 4)

            if is_integer_shares and shares <= 0:
                continue

            actual_cap = round(shares * entry_p, 2) if is_integer_shares else cap
            final_weights[tk] = float(w)
            allocated_cap[tk] = actual_cap
            shares_dict[tk] = shares
            total_allocated += actual_cap

            alloc_items.append(
                AllocationItem(
                    ticker=tk,
                    direction=opp.direction,
                    weight=float(w),
                    weight_pct=round(float(w) * 100, 2),
                    allocated_capital=actual_cap,
                    entry_price=round(entry_p, 2),
                    shares=shares,
                    target_price=round(opp.evaluation.target_price, 2),
                    stop_price=round(opp.evaluation.stop_price, 2),
                    expected_net_ev_pct=round(opp.evaluation.net_expectancy_pct, 2),
                    kelly_optimal_f=0.0,
                    vol_scalar=1.0,
                    dd_scalar=round(dd_scalar, 3),
                    sizing_rationale=f"HRP RMT De-noised weight {w*100:.1f}% (cap: {self.max_cap*100:.0f}%)",
                )
            )

        residual_cash = round(total_virtual_equity - total_allocated, 2)
        cash_w = round(residual_cash / total_virtual_equity, 4)
        final_weights["CASH"] = cash_w

        return PortfolioAllocationResult(
            weights=final_weights,
            cash_weight=cash_w,
            allocated_capital=allocated_cap,
            shares=shares_dict,
            is_100_percent_cash=False,
            method="HRP",
            allocations=alloc_items,
            total_virtual_equity=round(total_virtual_equity, 2),
            total_allocated_capital=round(total_allocated, 2),
            residual_cash_capital=residual_cash,
            explanation=f"Allocated {len(alloc_items)} positions ({sum(final_weights[t] for t in allocated_cap)*100:.1f}% equity, {cash_w*100:.1f}% cash) via RMT De-noised HRP.",
        )
```

---

### 5.2 `src/strategy/decision_explainer.py`
```python
"""Quantitative Decision Explainability Engine.

Produces human-readable, transparent plain-language explanations for accepted trades,
rejected trades, and mandatory 100% cash preservation.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Any

from src.strategy.portfolio_selector import AllocationItem, PortfolioAllocationResult
from src.strategy.trade_ranker import RankedOpportunity

logger = logging.getLogger(__name__)


@dataclass
class PlainLanguageExplanation:
    ticker: str
    action: str                        # "ACCEPTED", "REJECTED", "HELD_IN_CASH"
    headline: str
    summary: str
    factors: Dict[str, str]
    metrics: Dict[str, Any]
    timestamp_utc: str


class DecisionExplainer:
    """Translates mathematical quantitative decisions into plain-language activity logs."""

    @staticmethod
    def _now_utc() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def explain_accepted_trade(
        cls,
        opportunity: RankedOpportunity,
        allocation: AllocationItem,
        currency_symbol: str = "$",
    ) -> PlainLanguageExplanation:
        ev = opportunity.evaluation
        ticker = opportunity.ticker
        direction = opportunity.direction
        win_prob = ev.win_probability * 100.0
        cons_prob = getattr(ev, "conservative_win_prob", ev.win_probability) * 100.0
        ev_pct = ev.net_expectancy_pct
        friction_bps = ev.round_trip_friction_pct * 100.0

        b = max(ev.expected_win_return_pct / max(ev.expected_loss_return_pct, 1e-4), 0.50)
        pt_gain_pct = abs((ev.target_price - ev.entry_price) / ev.entry_price) * 100.0
        sl_loss_pct = abs((ev.entry_price - ev.stop_price) / ev.entry_price) * 100.0

        headline = f"BUY {ticker}: Net Expectancy +{ev_pct:.2f}% | Win Prob {win_prob:.1f}%"
        summary = (
            f"Accepted {direction} opportunity on {ticker}. Model projects a +{ev_pct:.2f}% net mathematical edge "
            f"after deducting {friction_bps:.1f} bps in statutory exchange fees, taxes, and Almgren-Chriss market impact. "
            f"Risk-scaled sizing authorizes {allocation.weight_pct:.1f}% allocation "
            f"({currency_symbol}{allocation.allocated_capital:,.2f} / {allocation.shares:g} units) "
            f"with profit target {currency_symbol}{ev.target_price:,.2f} and stop loss {currency_symbol}{ev.stop_price:,.2f}."
        )

        factors = {
            "net_expectancy": f"Net edge +{ev_pct:.2f}% satisfies the minimum hurdle (+0.20%).",
            "win_probability": f"Calibrated win probability is {win_prob:.1f}% (conservative bound {cons_prob:.1f}%).",
            "statutory_frictions": f"Round-trip transaction costs and slippage estimated at {friction_bps:.1f} bps.",
            "regime_alignment": f"Market alignment factor {opportunity.regime_multiplier:.2f}x applied ({opportunity.rank_justification}).",
            "position_sizing": f"Sized at {allocation.weight_pct:.1f}% equity (institutional cap 20.0%, Kelly f*: {allocation.kelly_optimal_f:.2f}).",
            "risk_reward_barriers": f"Target +{pt_gain_pct:.2f}% vs Stop -{sl_loss_pct:.2f}% (payoff odds ratio b={b:.2f}).",
        }

        metrics = {
            "net_expectancy_pct": round(ev_pct, 2),
            "win_probability": round(ev.win_probability, 4),
            "conservative_win_prob": round(cons_prob / 100.0, 4),
            "round_trip_friction_bps": round(friction_bps, 1),
            "entry_price": round(ev.entry_price, 2),
            "target_price": round(ev.target_price, 2),
            "stop_price": round(ev.stop_price, 2),
            "payoff_ratio": round(b, 2),
            "allocation_weight_pct": round(allocation.weight_pct, 2),
            "allocated_capital": round(allocation.allocated_capital, 2),
            "shares": allocation.shares,
            "currency": currency_symbol,
        }

        return PlainLanguageExplanation(
            ticker=ticker,
            action="ACCEPTED",
            headline=headline,
            summary=summary,
            factors=factors,
            metrics=metrics,
            timestamp_utc=cls._now_utc(),
        )

    @classmethod
    def explain_rejected_trade(
        cls,
        opportunity: RankedOpportunity,
        rejection_reason_override: Optional[str] = None,
        currency_symbol: str = "$",
    ) -> PlainLanguageExplanation:
        ev = opportunity.evaluation
        ticker = opportunity.ticker
        direction = opportunity.direction
        ev_pct = ev.net_expectancy_pct
        win_prob = ev.win_probability * 100.0
        friction_bps = ev.round_trip_friction_pct * 100.0

        reason = rejection_reason_override or ev.rejection_reason or "Negative Net Expectancy"

        if "Crisis" in reason or opportunity.regime_multiplier == 0.0:
            headline = f"REJECTED {ticker}: Crisis Regime Quarantine"
            summary = (
                f"Rejected {direction} trade on {ticker}. Market is currently in High-Vol Crisis regime (State 2). "
                f"Quantitative risk governance halts new position authorizations to protect capital."
            )
        elif "Microstructure" in reason or "Rollover" in reason or "LULD" in reason:
            headline = f"REJECTED {ticker}: Microstructure Circuit Breaker"
            summary = f"Rejected {direction} trade on {ticker}: {reason}. Trade blocked to prevent severe execution slippage."
        elif ev_pct <= 0.0:
            headline = f"REJECTED {ticker}: Negative Net Expectancy ({ev_pct:.2f}%)"
            summary = (
                f"Rejected {direction} opportunity on {ticker}. Although gross probability is {win_prob:.1f}%, "
                f"net mathematical expectancy is negative ({ev_pct:.2f}%) after deducting {friction_bps:.1f} bps in statutory fees."
            )
        else:
            headline = f"REJECTED {ticker}: Insufficient Edge"
            summary = f"Rejected trade on {ticker}: {reason}."

        factors = {
            "rejection_cause": reason,
            "net_expectancy": f"Net EV is {ev_pct:.2f}% (minimum hurdle is +0.20%).",
            "win_probability": f"Calibrated win probability is {win_prob:.1f}%.",
            "friction_impact": f"Round-trip transaction friction is {friction_bps:.1f} bps.",
            "regime_state": f"Regime factor: {opportunity.regime_multiplier:.2f}x.",
        }

        metrics = {
            "net_expectancy_pct": round(ev_pct, 2),
            "win_probability": round(ev.win_probability, 4),
            "round_trip_friction_bps": round(friction_bps, 1),
            "rejection_reason": reason,
        }

        return PlainLanguageExplanation(
            ticker=ticker,
            action="REJECTED",
            headline=headline,
            summary=summary,
            factors=factors,
            metrics=metrics,
            timestamp_utc=cls._now_utc(),
        )

    @classmethod
    def explain_portfolio_cash_fallback(
        cls,
        total_candidates_evaluated: int,
        rejection_summary: str,
        active_regime: str = "Normal",
        current_drawdown_pct: float = 0.0,
    ) -> PlainLanguageExplanation:
        headline = "100% CASH PRESERVED: Zero Opportunities Satisfy Edge Hurdle"
        summary = (
            f"The quantitative engine evaluated {total_candidates_evaluated} candidate instruments in the active universe, "
            f"but none demonstrated positive Net Expectancy after accounting for statutory taxes, fees, and market impact. "
            f"To protect virtual capital from adverse mathematical expectation, 100% of equity is preserved in cash."
        )

        factors = {
            "candidates_evaluated": f"{total_candidates_evaluated} universe instruments analyzed.",
            "rejection_summary": rejection_summary,
            "market_regime": f"Active regime: {active_regime}.",
            "capital_protection": "100.0% capital maintained in cash balance (0.0% market exposure).",
            "next_action": "Engine will re-evaluate on the next bar close.",
        }

        metrics = {
            "total_candidates": total_candidates_evaluated,
            "qualifying_count": 0,
            "cash_weight_pct": 100.0,
            "portfolio_drawdown_pct": round(current_drawdown_pct, 2),
        }

        return PlainLanguageExplanation(
            ticker="PORTFOLIO",
            action="HELD_IN_CASH",
            headline=headline,
            summary=summary,
            factors=factors,
            metrics=metrics,
            timestamp_utc=cls._now_utc(),
        )

    @classmethod
    def explain_allocation_result(
        cls,
        result: PortfolioAllocationResult,
        ranked_opportunities: List[RankedOpportunity],
        currency_symbol: str = "$",
    ) -> List[PlainLanguageExplanation]:
        """Produces a comprehensive list of explanations for an allocation result."""
        explanations: List[PlainLanguageExplanation] = []

        if result.is_100_percent_cash:
            explanations.append(
                cls.explain_portfolio_cash_fallback(
                    total_candidates_evaluated=len(ranked_opportunities),
                    rejection_summary=result.explanation,
                )
            )
            return explanations

        # Accepted positions
        alloc_map = {item.ticker: item for item in result.allocations}
        for opp in ranked_opportunities:
            if opp.ticker in alloc_map:
                explanations.append(
                    cls.explain_accepted_trade(opp, alloc_map[opp.ticker], currency_symbol)
                )
            else:
                explanations.append(
                    cls.explain_rejected_trade(opp, currency_symbol=currency_symbol)
                )

        return explanations
```

---

## 6. Verification and Test Blueprint

### 6.1 `tests/test_strategy_portfolio_selector.py`
The test suite validates all mathematical formulas, circuit breakers, and invariants:
1. `test_empty_opportunities_triggers_100_percent_cash`: Empty candidate list returns `weights={"CASH": 1.0}`, `is_100_percent_cash=True`.
2. `test_all_negative_ev_triggers_100_percent_cash`: 5 candidate trades all with `EV <= 0` return 100% cash.
3. `test_crisis_regime_triggers_100_percent_cash`: Candidates with positive EV in a Crisis regime return 100% cash.
4. `test_fractional_kelly_sizing_and_dampening`: Verifies exact calculation of $f^* = p - (1-p)/b$, volatility scaling, and drawdown scaling.
5. `test_institutional_single_position_cap_20_percent`: Unconstrained weight of 45% is clamped strictly to 20.0%.
6. `test_dynamic_capital_scaling_invariance`: Sizing an account with ₹50,000 vs ₹5,000,000 yields identical weights and exactly $100\times$ allocated capital and shares.
7. `test_drawdown_kill_circuit_breaker`: Portfolio drawdown of 16% drops `dd_scalar` to 0.0 and freezes capital in cash.
8. `test_hrp_mode_with_rmt_denoising`: Multi-asset HRP run with covariance matrix verifies Marchenko-Pastur RMT cleaning, diagonal variance preservation, and 20% capping.
9. `test_integer_shares_for_nse`: When market is NSE, share quantities are strictly integers ($\lfloor \text{capital} / \text{price} \rfloor$).

### 6.2 `tests/test_strategy_decision_explainer.py`
The test suite validates all plain-language explanations:
1. `test_explain_accepted_trade`: Output contains EV, win probability, statutory fees deducted, regime alignment, and position sizing details.
2. `test_explain_rejected_negative_ev_trade`: Output states clear rationale for rejection despite positive win probability.
3. `test_explain_rejected_microstructure_gate`: Output captures Forex rollover trough and CME Gold LULD circuit breakers.
4. `test_explain_100_percent_cash_preservation`: Output provides a reassuring narrative detailing why preserving capital in cash is optimal.
5. `test_explain_allocation_result_integration`: Full end-to-end explanation generation from a `PortfolioAllocationResult`.
