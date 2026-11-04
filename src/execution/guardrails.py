"""Risk Governance & Drawdown Guardrails Module.

Implements Asymmetric Fractional Kelly sizing with CVaR / Kurtosis tail-risk
dampening, target volatility scaling, and convex drawdown circuit breakers.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import numpy as np


@dataclass
class RiskAllocationDecision:
    authorized: bool
    authorized_weight_pct: float
    sizing_scalar: float
    circuit_breaker_active: bool
    drawdown_pct: float
    status_message: str


class RiskGuardrailEngine:
    """Enforces asymmetric Kelly bet sizing, CVaR tail bounds, and drawdown safety controls."""

    def __init__(
        self,
        kelly_fraction: float = 0.30,
        target_annual_vol: float = 0.15,
        warning_drawdown: float = 0.08,
        max_kill_drawdown: float = 0.15,
        convex_power: float = 2.0,
        max_position_cap: float = 0.20,
    ):
        self.kelly_c = kelly_fraction
        self.target_vol = target_annual_vol
        self.dd_warn = warning_drawdown
        self.dd_kill = max_kill_drawdown
        self.convex_p = convex_power
        self.max_cap = max_position_cap

    def evaluate_allocation(
        self,
        current_drawdown: float,
        model_bet_size: float,
        realized_annual_vol: float,
        win_probability: Optional[float] = None,
        payoff_ratio_b: float = 1.5,
        excess_kurtosis: float = 0.0,
        cvar_95_daily: Optional[float] = None,
    ) -> RiskAllocationDecision:
        """Calculates final safe position weight under CVaR-constrained asymmetric Kelly.

        Args:
            current_drawdown: Portfolio current drawdown fraction [0.0, 1.0]
            model_bet_size: Rectified directional conviction in [-1.0, 1.0]
            realized_annual_vol: Annualized asset volatility (e.g. 0.25 for 25%)
            win_probability: Optional explicit calibrated win probability p in [0.0, 1.0]
            payoff_ratio_b: Asymmetric payoff odds ratio b = Avg Win / Avg Loss
            excess_kurtosis: Asset return excess kurtosis for fat-tail penalty
            cvar_95_daily: Optional 95% daily Conditional Value-at-Risk fraction
        """
        # 1. Hard Circuit Breaker Check
        if current_drawdown >= self.dd_kill:
            return RiskAllocationDecision(
                authorized=False,
                authorized_weight_pct=0.0,
                sizing_scalar=0.0,
                circuit_breaker_active=True,
                drawdown_pct=round(current_drawdown * 100, 2),
                status_message=f"CIRCUIT BREAKER TRIGGERED: Drawdown {current_drawdown:.1%} exceeded {self.dd_kill:.1%} limit. All capital frozen in cash.",
            )

        # 2. Asymmetric Fractional Kelly Sizing: f* = p - (1 - p) / b
        b = max(float(payoff_ratio_b), 0.5)
        if win_probability is not None:
            p = float(np.clip(win_probability, 0.0, 1.0))
            asymmetric_kelly = max(0.0, p - ((1.0 - p) / b))
            base_edge = min(abs(model_bet_size), asymmetric_kelly) if abs(model_bet_size) > 0 else 0.0
        else:
            # Derive implied p from rectified model_bet_size = 2p - 1
            p_implied = 0.5 * (abs(model_bet_size) + 1.0)
            asymmetric_kelly = max(0.0, p_implied - ((1.0 - p_implied) / b))
            base_edge = max(abs(model_bet_size), asymmetric_kelly) if abs(model_bet_size) > 0 else 0.0

        # Higher-moment fat-tail penalty (reduces Kelly fraction under leptokurtic jump risk)
        kurt_penalty = 1.0 / (1.0 + 0.15 * max(0.0, float(excess_kurtosis)))
        raw_weight = base_edge * self.kelly_c * kurt_penalty

        # 3. Volatility & CVaR Tail Dampening
        vol_safe = max(realized_annual_vol, 0.05)
        vol_scalar = min(1.0, self.target_vol / vol_safe)

        if cvar_95_daily is not None and cvar_95_daily > 0.025:
            cvar_scalar = min(1.0, 0.025 / float(cvar_95_daily))
            vol_scalar *= cvar_scalar

        # 4. Convex Drawdown Dampening
        if current_drawdown < self.dd_warn:
            dd_scalar = 1.0
        else:
            excess = current_drawdown - self.dd_warn
            scale_range = max(self.dd_kill - self.dd_warn, 1e-4)
            dd_scalar = max(0.0, (1.0 - (excess / scale_range))) ** self.convex_p

        # Composite sizing multiplier
        total_scalar = vol_scalar * dd_scalar
        final_weight = raw_weight * total_scalar

        # Hard institutional single-position leverage ceiling (20%)
        final_weight = min(final_weight, self.max_cap)

        status = "NORMAL_OPERATION" if dd_scalar == 1.0 else "DRAWDOWN_DAMPENED"

        return RiskAllocationDecision(
            authorized=final_weight > 0.01,
            authorized_weight_pct=round(final_weight * 100, 2),
            sizing_scalar=round(total_scalar, 3),
            circuit_breaker_active=False,
            drawdown_pct=round(current_drawdown * 100, 2),
            status_message=f"{status}: Sizing scaled by {total_scalar:.2f}x (Vol: {vol_scalar:.2f}x, DD: {dd_scalar:.2f}x)",
        )
