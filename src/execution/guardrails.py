"""Risk Governance & Drawdown Guardrails Module.

Implements Asymmetric Fractional Kelly sizing with CVaR / Kurtosis tail-risk
dampening, target volatility scaling, and convex drawdown circuit breakers.
"""

from dataclasses import dataclass
import threading
import time
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


class TokenBucketRateLimiter:
    """Thread-safe Token Bucket Rate Limiter to throttle algorithmic order submission.

    Capped well below 10 orders/sec (default: rate=5.0 tokens/second, burst capacity=5.0 tokens).
    SEBI/NSE algorithmic trading guidelines restrict order throughput to prevent runaway algo submission.
    """

    def __init__(self, rate: float = 5.0, capacity: float = 5.0):
        self.rate = float(rate)
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.last_update = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> bool:
        """Attempts to consume tokens. Returns True if granted, False if throttled."""
        with self._lock:
            now = time.monotonic()
            elapsed = max(0.0, now - self.last_update)
            self.last_update = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """Alias for acquire()."""
        return self.acquire(tokens=tokens)

    def check(self, tokens: float = 1.0) -> bool:
        """Non-consuming inspection of available tokens."""
        with self._lock:
            now = time.monotonic()
            elapsed = max(0.0, now - self.last_update)
            current_tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            return current_tokens >= tokens

    def wait_and_acquire(self, tokens: float = 1.0, timeout: Optional[float] = None) -> bool:
        """Blocks until tokens are available or timeout expires."""
        start = time.monotonic()
        while True:
            if self.acquire(tokens):
                return True
            if timeout is not None and (time.monotonic() - start) >= timeout:
                return False
            time.sleep(0.01)

    def reset(self) -> None:
        """Resets the bucket to full capacity."""
        with self._lock:
            self.tokens = float(self.capacity)
            self.last_update = time.monotonic()


def validate_nse_order_type(
    ticker: str,
    order_type: str,
    limit_price: Optional[float] = None,
    current_price: Optional[float] = None,
    direction: str = "LONG",
    convert_if_market: bool = True,
    lpp_pct: float = 0.01,
) -> Tuple[str, Optional[float], Optional[str]]:
    """Enforces SEBI/NSE regulations prohibiting automated algorithmic MARKET orders.

    NSE mandates that algorithmic systems submit LIMIT orders with Limit Price Protection (LPP)
    to protect against unexpected order book sweeps.

    Args:
        ticker: Asset ticker symbol.
        order_type: Requested order type (MARKET or LIMIT).
        limit_price: Explicit limit price, if provided.
        current_price: Current reference market price.
        direction: LONG or SHORT.
        convert_if_market: If True, converts MARKET to LIMIT with LPP. If False, raises ValueError.
        lpp_pct: Limit Price Protection buffer fraction (default 1.0% = 0.01).

    Returns:
        Tuple of (effective_order_type, effective_limit_price, explanatory_message)
    """
    tk = (ticker or "").strip().upper()
    is_nse = tk.endswith((".NS", ".BO")) or tk.startswith(("^NSE", "^BS"))
    ord_type = (order_type or "MARKET").strip().upper()

    if not is_nse or ord_type != "MARKET":
        return ord_type, limit_price, None

    if not convert_if_market:
        raise ValueError(
            f"Algorithmic MARKET orders are strictly prohibited for NSE symbol '{ticker}'. "
            f"NSE regulations require LIMIT orders with limit price protection (LPP)."
        )

    ref_p = limit_price if (limit_price and limit_price > 0) else (current_price or 100.0)
    dir_upper = (direction or "LONG").strip().upper()
    if dir_upper == "LONG":
        lpp_price = round(ref_p * (1.0 + lpp_pct), 2)
    else:
        lpp_price = round(ref_p * (1.0 - lpp_pct), 2)

    msg = (
        f"NSE Algo Invariant: MARKET order for {tk} converted to LIMIT with "
        f"{lpp_pct * 100.0:.1f}% Limit Price Protection (limit_price={lpp_price}) per NSE regulations."
    )
    return "LIMIT", lpp_price, msg

