"""Portfolio Allocation & Sizing Engine (Fractional Kelly & De-noised HRP).

Enforces asymmetric Fractional Kelly sizing, Marchenko-Pastur RMT de-noised HRP,
single-position 20% leverage ceiling, and mandatory 100% Cash Allocation Guarantee.
"""

from dataclasses import asdict, dataclass
import logging
import math
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from src.models.hrp_allocator import HierarchicalRiskParity
from src.strategy.trade_ranker import RankedOpportunity

logger = logging.getLogger(__name__)


@dataclass
class AllocationItem:
    """Detailed allocation metrics for an individual qualifying instrument."""

    ticker: str
    direction: str  # "LONG" or "SHORT"
    weight: float  # Fraction of portfolio [0.0, 0.20]
    weight_pct: float  # Percentage (e.g. 15.5%)
    allocated_capital: float  # Dollar/Rupee amount allocated
    entry_price: float  # Benchmark reference entry price
    shares: float  # Calculated share/unit quantity
    target_price: float  # Upper profit target
    stop_price: float  # Lower stop loss
    expected_net_ev_pct: float  # Net Expectancy %
    kelly_optimal_f: float  # Unconstrained Kelly fraction f*
    vol_scalar: float  # Volatility dampening scalar
    dd_scalar: float  # Drawdown dampening scalar
    sizing_rationale: str  # Concise summary of sizing drivers

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PortfolioAllocationResult:
    """Master portfolio allocation decision structure."""

    weights: Dict[str, float]  # ticker -> weight, and "CASH" -> cash_weight
    cash_weight: float  # Proportion in cash [0.0, 1.0]
    allocated_capital: Dict[str, float]  # ticker -> allocated currency amount
    shares: Dict[str, float]  # ticker -> share quantity
    is_100_percent_cash: bool  # Flag indicating complete capital preservation
    method: str  # "KELLY" or "HRP"
    allocations: List[AllocationItem]  # Granular asset allocations
    total_virtual_equity: float  # Starting virtual capital
    total_allocated_capital: float  # Total capital deployed in positions
    residual_cash_capital: float  # Capital retained in cash balance
    explanation: str  # Executive summary of allocation decision

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["allocations"] = [a.to_dict() for a in self.allocations]
        return d


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
        self.integer_markets = integer_shares_markets or [
            "NSE_CASH",
            "NSE",
            "INDIAN_NSE",
            "BSE",
            "INDIA",
        ]

    def _compute_drawdown_scalar(self, current_drawdown: float) -> float:
        """Computes convex drawdown dampening scalar in [0.0, 1.0]."""
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
        """Constructs mandatory 100% Cash Allocation Result."""
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
        """Master allocation method enforcing the 100% Cash Allocation Guarantee."""
        if total_virtual_equity <= 0.0:
            raise ValueError(
                f"Total virtual equity must be positive, got {total_virtual_equity}"
            )

        # 1. Hard Drawdown circuit breaker
        dd_scalar = self._compute_drawdown_scalar(current_drawdown)
        if dd_scalar <= 0.0:
            return self._create_100_percent_cash_result(
                total_virtual_equity,
                method,
                f"Portfolio drawdown ({current_drawdown:.1%}) breached kill limit ({self.dd_kill:.1%}). Capital frozen in cash.",
            )

        # 2. Filter strictly for eligible, positive Net Expectancy trades
        eligible = [
            opp
            for opp in ranked_opportunities
            if opp.is_eligible
            and opp.evaluation.is_positive_ev
            and opp.evaluation.net_expectancy_pct > 0.0
        ]

        # 3. Mandatory 100% Cash Allocation Guarantee if no qualifying opportunities
        if not eligible:
            return self._create_100_percent_cash_result(
                total_virtual_equity,
                method,
                "Zero candidate opportunities met positive Net Expectancy hurdle (EV > 0). Capital preserved in cash.",
            )

        method_upper = method.upper()
        if (
            method_upper == "HRP"
            and len(eligible) >= 2
            and returns_df is not None
            and not returns_df.empty
        ):
            return self._allocate_hrp(
                eligible, total_virtual_equity, returns_df, dd_scalar, market_type
            )
        else:
            return self._allocate_kelly(
                eligible, total_virtual_equity, dd_scalar, market_type
            )

    def _allocate_kelly(
        self,
        opportunities: List[RankedOpportunity],
        total_virtual_equity: float,
        dd_scalar: float,
        market_type: str,
    ) -> PortfolioAllocationResult:
        """Allocates capital using Fractional Kelly sizing with institutional risk scaling."""
        raw_weights: Dict[str, float] = {}
        alloc_metrics: Dict[str, Dict[str, float]] = {}

        for opp in opportunities:
            ev = opp.evaluation
            p = float(getattr(ev, "conservative_win_prob", ev.win_probability))
            b = max(
                ev.expected_win_return_pct / max(ev.expected_loss_return_pct, 1e-4),
                0.50,
            )

            # Unconstrained Kelly fraction: f* = p - (1-p)/b
            f_star = p - ((1.0 - p) / b)
            if f_star <= 0.0:
                continue

            # Volatility scalar (adapt target vol ceiling for higher-volatility Crypto markets)
            annual_vol = float(ev.evaluation_metadata.get("annualized_vol", 0.20))
            effective_target_vol = (
                max(self.target_vol, 0.45)
                if market_type.upper() == "CRYPTO"
                else self.target_vol
            )
            vol_scalar = min(1.0, effective_target_vol / max(annual_vol, 0.05))

            w_raw = self.kelly_c * f_star * vol_scalar * dd_scalar
            w_capped = min(w_raw, self.max_cap)

            if w_capped > 0.005:  # Minimum 0.5% allocation threshold
                raw_weights[opp.ticker] = w_capped
                alloc_metrics[opp.ticker] = {
                    "f_star": f_star,
                    "vol_scalar": vol_scalar,
                }

        if not raw_weights:
            return self._create_100_percent_cash_result(
                total_virtual_equity,
                "KELLY",
                "Kelly optimization yielded 0.0% weight across all candidates after risk dampening.",
            )

        # Normalize if aggregate weights exceed max_gross
        total_w = sum(raw_weights.values())
        norm_factor = (
            min(1.0, self.max_gross / total_w)
            if total_w > self.max_gross
            else 1.0
        )

        final_weights: Dict[str, float] = {}
        allocated_cap: Dict[str, float] = {}
        shares_dict: Dict[str, float] = {}
        alloc_items: List[AllocationItem] = []
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

            shares = (
                float(math.floor(cap / entry_p))
                if is_integer_shares
                else round(cap / entry_p, 4)
            )
            if is_integer_shares and shares <= 0:
                continue

            actual_cap = (
                round(shares * entry_p, 2) if is_integer_shares else cap
            )
            final_weights[opp.ticker] = w
            allocated_cap[opp.ticker] = actual_cap
            shares_dict[opp.ticker] = shares
            total_allocated += actual_cap

            p_decimals = 4 if (entry_p < 10.0 or market_type.upper() == "FOREX") else 2
            metrics = alloc_metrics.get(opp.ticker, {"f_star": 0.0, "vol_scalar": 1.0})
            alloc_items.append(
                AllocationItem(
                    ticker=opp.ticker,
                    direction=opp.direction,
                    weight=w,
                    weight_pct=round(w * 100, 2),
                    allocated_capital=actual_cap,
                    entry_price=round(entry_p, p_decimals),
                    shares=shares,
                    target_price=round(opp.evaluation.target_price, p_decimals),
                    stop_price=round(opp.evaluation.stop_price, p_decimals),
                    expected_net_ev_pct=round(
                        opp.evaluation.net_expectancy_pct, 2
                    ),
                    kelly_optimal_f=round(metrics["f_star"], 4),
                    vol_scalar=round(metrics["vol_scalar"], 3),
                    dd_scalar=round(dd_scalar, 3),
                    sizing_rationale=(
                        f"Fractional Kelly {w*100:.1f}% (cap: {self.max_cap*100:.0f}%, "
                        f"f*: {metrics['f_star']:.2f}, vol_scalar: {metrics['vol_scalar']:.2f})"
                    ),
                )
            )

        if not final_weights:
            return self._create_100_percent_cash_result(
                total_virtual_equity,
                "KELLY",
                "Allocated capital was insufficient to buy minimum unit shares; 100% held in cash.",
            )

        residual_cash = round(total_virtual_equity - total_allocated, 2)
        cash_w = round(residual_cash / total_virtual_equity, 4)
        final_weights["CASH"] = cash_w

        deployed_pct = sum(final_weights[t] for t in allocated_cap) * 100.0
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
            explanation=(
                f"Allocated {len(alloc_items)} positions ({deployed_pct:.1f}% equity, "
                f"{cash_w*100:.1f}% cash) via Fractional Kelly."
            ),
        )

    def _allocate_hrp(
        self,
        opportunities: List[RankedOpportunity],
        total_virtual_equity: float,
        returns_df: pd.DataFrame,
        dd_scalar: float,
        market_type: str,
    ) -> PortfolioAllocationResult:
        """Allocates capital via Marchenko-Pastur RMT de-noised HRP with iterative 20% capping."""
        eligible_tickers = [
            opp.ticker for opp in opportunities if opp.ticker in returns_df.columns
        ]
        if len(eligible_tickers) < 2:
            return self._allocate_kelly(
                opportunities, total_virtual_equity, dd_scalar, market_type
            )

        sub_returns = returns_df[eligible_tickers].dropna()
        raw_hrp = HierarchicalRiskParity.compute_hrp_weights(sub_returns)

        # Iterative 20% position capping
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

            cap = round(total_virtual_equity * float(w), 2)
            entry_p = max(opp.evaluation.entry_price, 1e-4)
            shares = (
                float(math.floor(cap / entry_p))
                if is_integer_shares
                else round(cap / entry_p, 4)
            )

            if is_integer_shares and shares <= 0:
                continue

            actual_cap = (
                round(shares * entry_p, 2) if is_integer_shares else cap
            )
            final_weights[tk] = float(w)
            allocated_cap[tk] = actual_cap
            shares_dict[tk] = shares
            total_allocated += actual_cap

            p_decimals = 4 if (entry_p < 10.0 or market_type.upper() == "FOREX") else 2
            alloc_items.append(
                AllocationItem(
                    ticker=tk,
                    direction=opp.direction,
                    weight=float(w),
                    weight_pct=round(float(w) * 100, 2),
                    allocated_capital=actual_cap,
                    entry_price=round(entry_p, p_decimals),
                    shares=shares,
                    target_price=round(opp.evaluation.target_price, p_decimals),
                    stop_price=round(opp.evaluation.stop_price, p_decimals),
                    expected_net_ev_pct=round(
                        opp.evaluation.net_expectancy_pct, 2
                    ),
                    kelly_optimal_f=0.0,
                    vol_scalar=1.0,
                    dd_scalar=round(dd_scalar, 3),
                    sizing_rationale=(
                        f"HRP RMT De-noised weight {w*100:.1f}% (cap: {self.max_cap*100:.0f}%)"
                    ),
                )
            )

        if not final_weights:
            return self._create_100_percent_cash_result(
                total_virtual_equity,
                "HRP",
                "Allocated capital was insufficient to buy minimum unit shares; 100% held in cash.",
            )

        residual_cash = round(total_virtual_equity - total_allocated, 2)
        cash_w = round(residual_cash / total_virtual_equity, 4)
        final_weights["CASH"] = cash_w

        deployed_pct = sum(final_weights[t] for t in allocated_cap) * 100.0
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
            explanation=(
                f"Allocated {len(alloc_items)} positions ({deployed_pct:.1f}% equity, "
                f"{cash_w*100:.1f}% cash) via RMT De-noised HRP."
            ),
        )
