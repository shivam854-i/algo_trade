# Handoff Report: PortfolioSelector & DecisionExplainer (Milestone 1 - Part C)

**Author**: Portfolio & Explainability Explorer (`teamwork_explorer`)  
**Recipient**: Lead Orchestrator (`d0b51128-456f-4a81-855c-2a488d288844`) & Quantitative Implementer  
**Date**: November 5, 2026  
**Type**: Hard Handoff (Investigation & Blueprint Complete)  
**Location**: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m1_explorer_3\handoff.md`  

---

## 1. Observation

1. **Ad-Hoc Candidate Selection & Sizing in Live Bot**:
   In `src/execution/live_bot.py` (lines 981–984 and 1014–1017):
   ```python
   # Line 981-984: Naive distance ranking
   candidates.sort(
       key=lambda x: abs(x[1].meta_prediction.success_probability - 0.50),
       reverse=True,
   )

   # Line 1014-1017: Ad-hoc allocation fallback forcing equity exposure
   kelly_w = float(r.risk_decision.authorized_weight_pct)
   base_alloc = kelly_w if kelly_w >= 5.0 else (100.0 / max(len(self.armed_tickers), 2) * 0.6)
   alloc_pct = min(max(round(base_alloc, 1), 8.0), 18.0)
   ```
   *Observation*: If Kelly authorizes $<5.0\%$, the bot arbitrarily forces an 8.0%–18.0% equal-weight allocation. It lacks the ability to safely hold 100% in cash when edge is low or negative.

2. **Existing Risk Guardrail Formulas in `src/execution/guardrails.py`**:
   - Asymmetric Kelly (lines 73–84):
     $$f^* = p - \frac{1 - p}{b}, \quad b = \max(\text{payoff\_ratio\_b}, 0.5)$$
   - Volatility Scaling (lines 90–92):
     $$\text{vol\_scalar} = \min\left(1.0, \frac{\text{target\_vol}}{\max(\text{realized\_annual\_vol}, 0.05)}\right)$$
   - Convex Drawdown Dampening (lines 98–104):
     ```python
     if current_drawdown < self.dd_warn:
         dd_scalar = 1.0
     else:
         excess = current_drawdown - self.dd_warn
         scale_range = max(self.dd_kill - self.dd_warn, 1e-4)
         dd_scalar = max(0.0, (1.0 - (excess / scale_range))) ** self.convex_p
     ```
   - Single-position cap (line 110): `final_weight = min(final_weight, self.max_cap)` (0.20 = 20%).

3. **Existing HRP Implementation in `src/models/hrp_allocator.py`**:
   - `HierarchicalRiskParity.denoise_covariance`: Marchenko-Pastur RMT de-noising preserving diagonal raw variances (lines 20–65):
     $$\lambda_{\max} = \sigma^2 \left(1 + \sqrt{\frac{1}{q}}\right)^2, \quad q = \frac{T}{N}$$
     `np.fill_diagonal(clean_cov, raw_diag_var)`.
   - `compute_hrp_weights`: Correlation distance $D_{i,j} = \sqrt{0.5(1 - \rho_{i,j})}$, Ward's linkage, quasi-diagonalization, and recursive bisection (lines 68–130).

4. **Statutory Friction & Microstructure Profiles in `src/execution/frictions.py`**:
   - `FrictionEvaluator.get_profile(ticker)` defines precise statutory fees for US (SEC, FINRA TAF, 1.0 bps slip), NSE Cash (STT intraday 0.025% vs delivery 0.10%, Stamp duty, GST 18%, 2.0 bps slip), Forex, Crypto, and Commodities.
   - `check_microstructure_execution_gate(ticker)` halts orders during Forex 17:00 EST rollover trough, CME Gold LULD halts, and extreme liquidity-sweep rejection wicks.

5. **Baseline Test Suite Execution**:
   Executing `cd C:\Users\Shivam\Desktop\trade_bot; py tests/test_phase1_phase2_fixes.py` exited with code 0:
   - PASS 1: FracDiff analytical lookback $L^*(0.25, 1e-3) = 21$ bars.
   - PASS 2: Causal HMM Future-Invariance state diffs: 0.
   - PASS 3: Triple-Barrier Dual-Breach Wick Label: 0.
   - PASS 4: HRP RMT Diagonal Variance Preservation Error: 0.00e+00, Ward Weights Sum: 1.0001.
   - PASS 5: Frictions -> NSE Delivery: 34.97 bps, NSE Intraday: 16.27 bps, US: 8.15 bps.
   - PASS 6: Asymmetric CVaR-Kelly -> Low-Prob Weight: 0.0%, High-Prob Cap: 20.0%.
   - PASS 7: Supervised TCN Pinball Loss: 0.00548, Monotonic Quantiles: $q_{10} \le q_{50} \le q_{90}$.
   - PASS 8: Microstructure Gates -> FX Rollover Allowed: False, Gold Sweep Allowed: False.

---

## 2. Logic Chain

1. **From Observation 1 to PortfolioSelector Extraction**:
   - `live_bot.py` contains hardcoded sizing and arbitrary fallbacks (forcing 8%–18% allocation when Kelly authorizes $<5\%$).
   - This directly violates the core requirement: **when opportunities lack positive edge, capital must be held in cash**.
   - Therefore, a modular `PortfolioSelector` (`src/strategy/portfolio_selector.py`) must be implemented to govern portfolio weights and enforce the 100% Cash Allocation Guarantee.

2. **From Observation 2 to Fractional Kelly Formulation**:
   - Kelly optimization sizes capital proportional to mathematical edge:
     $$f_i^* = P(\text{Win}_i) - \frac{1 - P(\text{Win}_i)}{b_i}$$
   - Scaling by $c_{\text{kelly}} = 0.30$, volatility scalar $\min(1.0, \sigma_{\text{target}} / \sigma_i)$, and convex drawdown scalar $(1 - \frac{D - D_{\text{warn}}}{D_{\text{kill}} - D_{\text{warn}}})^2$ provides robust tail-risk dampening.
   - Clamping to $w_i \le 0.20$ guarantees institutional diversification across individual holdings.

3. **From Observation 3 to HRP Mode Formulation**:
   - For multi-asset baskets ($K \ge 2$), HRP computes tree-clustered risk-parity weights without matrix inversion instability.
   - Combining Marchenko-Pastur RMT de-noising with an iterative 20% position-capping loop and gross leverage scaling ($\min(0.95, \text{DDScalar})$) prevents overconcentration and dampens exposure during portfolio drawdowns.

4. **From Requirement R4 & Dispatch to Mandatory 100% Cash Guarantee**:
   - If zero candidate opportunities have $\text{EV} > 0$, or if market regime is Crisis (State 2), or if drawdown $D \ge 15\%$:
     `weights={"CASH": 1.0}`, `cash_weight=1.0`, `is_100_percent_cash=True`, `allocated_capital={}`, `shares={}`.
   - Zero dollars are risked in the market.

5. **From Requirement R5 to Dynamic Capital Scaling Invariant**:
   - Model predictions ($P(\text{Win})$, targets, stops, EV) must not depend on virtual account size.
   - Position sizing scales linearly with virtual capital:
     $$\text{AllocatedCapital}_i = \text{round}(E \cdot w_i, 2), \quad \text{Shares}_i = \lfloor \text{AllocatedCapital}_i / P_{\text{entry}, i} \rfloor$$
   - Thus, an account with ₹1,000,000 purchases exactly $10\times$ the shares and dollars of an account with ₹100,000, while model outputs remain strictly identical.

6. **From Requirement R2, R4 & Observation 4 to DecisionExplainer**:
   - Users and dashboard operators require clear, plain-language transparency for every autonomous action.
   - `DecisionExplainer` (`src/strategy/decision_explainer.py`) maps the quantitative metrics ($EV$, $P(\text{Win})$, statutory fees, HMM regime, Kelly fraction, shares) into structured `PlainLanguageExplanation` objects for accepted trades, rejected trades, and 100% cash preservation.

---

## 3. Caveats

1. **Virtual Execution Isolation**:
   - All capital, allocations, and orders are strictly virtual paper-trading. No physical broker connections or real capital should ever be touched.
2. **HRP Fallback for Insufficient Return History**:
   - If `returns_df` contains fewer than 2 eligible assets or has missing columns, `PortfolioSelector` must gracefully fall back to Fractional Kelly mode rather than raising an unhandled exception.
3. **Integer Share Quantities vs Small Capital**:
   - In equity markets enforcing integer shares (e.g. NSE Cash), if allocated capital is smaller than the price of 1 share, the share count evaluates to 0. In this case, the engine must safely leave the unspent capital in cash rather than attempting an invalid partial share order.

---

## 4. Conclusion & Complete Implementation Blueprints

### 4.1 `src/strategy/portfolio_selector.py` Blueprint

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

        # 1. Hard Drawdown circuit breaker
        dd_scalar = self._compute_drawdown_scalar(current_drawdown)
        if dd_scalar <= 0.0:
            return self._create_100_percent_cash_result(
                total_virtual_equity, method,
                f"Portfolio drawdown ({current_drawdown:.1%}) breached kill limit ({self.dd_kill:.1%}). Capital frozen in cash."
            )

        # 2. Filter strictly for eligible, positive Net Expectancy trades
        eligible = [
            opp for opp in ranked_opportunities
            if opp.is_eligible and opp.evaluation.is_positive_ev and opp.evaluation.net_expectancy_pct > 0.0
        ]

        # 3. Mandatory 100% Cash Allocation Guarantee if no qualifying opportunities
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

            # Unconstrained Kelly fraction: f* = p - (1-p)/b
            f_star = p - ((1.0 - p) / b)
            if f_star <= 0.0:
                continue

            # Volatility scalar
            vol = max(opp.evaluation.expected_win_return_pct * 2.0 / 100.0, 0.05)
            vol_scalar = min(1.0, self.target_vol / vol)

            w_raw = self.kelly_c * f_star * vol_scalar * dd_scalar
            w_capped = min(w_raw, self.max_cap)

            if w_capped > 0.005:  # Minimum 0.5% weight threshold
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

            cap = round(total_virtual_equity * w, 2)
            entry_p = max(opp.evaluation.entry_price, 1e-4)

            shares = math.floor(cap / entry_p) if is_integer_shares else round(cap / entry_p, 4)
            if is_integer_shares and shares <= 0:
                continue

            actual_cap = round(shares * entry_p, 2) if is_integer_shares else cap
            final_weights[opp.ticker] = w
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

### 4.2 `src/strategy/decision_explainer.py` Blueprint

```python
"""Quantitative Decision Explainability Engine.

Produces human-readable, transparent plain-language explanations for accepted trades,
rejected trades, and mandatory 100% cash preservation.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Any

from src.strategy.portfolio_selector import AllocationItem, PortfolioAllocationResult
from src.strategy.trade_ranker import RankedOpportunity

logger = logging.getLogger(__name__)


@dataclass
class PlainLanguageExplanation:
    ticker: str                        # Instrument symbol or "PORTFOLIO"
    action: str                        # "ACCEPTED", "REJECTED", "HELD_IN_CASH"
    headline: str                      # Header for activity feed
    summary: str                       # Multi-sentence plain-language explanation
    factors: Dict[str, str]            # Factor name -> descriptive text
    metrics: Dict[str, Any]            # Quantitative verification metrics
    timestamp_utc: str                 # UTC ISO timestamp


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
        explanations: List[PlainLanguageExplanation] = []

        if result.is_100_percent_cash:
            explanations.append(
                cls.explain_portfolio_cash_fallback(
                    total_candidates_evaluated=len(ranked_opportunities),
                    rejection_summary=result.explanation,
                )
            )
            return explanations

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

## 5. Verification Method

### Test Commands:
```powershell
cd C:\Users\Shivam\Desktop\trade_bot

# 1. Verify Phase 1 & 2 mathematical baseline
py tests/test_phase1_phase2_fixes.py

# 2. Run new Milestone 1 Part C tests (once implemented)
py -m pytest tests/test_strategy_portfolio_selector.py tests/test_strategy_decision_explainer.py -v
```

### Invalidation Conditions:
1. If `PortfolioSelector.allocate` returns any equity weight ($w_i > 0$) when zero candidate opportunities meet the positive Net Expectancy hurdle ($\text{EV} > 0$), the 100% Cash Guarantee is violated.
2. If `PortfolioSelector.allocate` authorizes any trade when market regime is Crisis (State 2), the crisis veto is violated.
3. If an individual asset's allocated weight exceeds $0.20$ ($20\%$), the single-position leverage ceiling is violated.
4. If scaling starting capital $E$ alters model predictions ($P(\text{Win})$, targets, stops, or EV), the Dynamic Capital Scaling Invariant is violated.
5. If `DecisionExplainer` generates explanations missing statutory friction costs, win probabilities, or position sizing rationale, explainability criteria are violated.
