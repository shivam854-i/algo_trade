"""Trade Expectancy Evaluator Module.

Computes mathematical Net Expectancy incorporating epistemic uncertainty bounds,
conditional payoff barriers, gap risk buffers, statutory frictions, and Almgren-Chriss
market impact.
"""

from dataclasses import asdict, dataclass, field
import logging
import math
from typing import Any, Dict, Optional, Tuple

from src.execution.frictions import FrictionEvaluator
from src.pipeline import SingleAssetAnalysis

logger = logging.getLogger(__name__)


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
    expected_loss_return_pct: float  # E[Loss | Loss] in % (includes gap risk buffer)
    gap_risk_buffer_pct: float  # 0.10 * sigma_bar in %
    round_trip_friction_pct: float  # Statutory + Almgren-Chriss slippage in %
    gross_expectancy_pct: float  # p_cons * E[Win] - (1 - p_cons) * E[Loss] in %
    net_expectancy_pct: float  # EV = gross_expectancy_pct - friction_pct in %
    min_ev_hurdle_pct: float = 0.20  # Minimum required EV hurdle (+0.20%)
    is_positive_ev: bool = False  # True iff net_expectancy_pct >= min_ev_hurdle
    rejection_reason: Optional[str] = None  # None if approved, else rationale
    payoff_ratio: float = 0.0  # b = E[Win] / max(E[Loss], 1e-4)
    evaluation_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def win_probability(self) -> float:
        """Alias returning conservative win probability for downstream consumers."""
        return self.conservative_win_prob

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
            sigma_p = sqrt(p * (1 - p) / min(n_bars, 250)) * (1.0 + 0.2 * (q90 - q10) / max(|q50|, 1e-4))
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
        micro_ok, micro_reason = FrictionEvaluator.check_microstructure_execution_gate(
            ticker, ohlcv_df=analysis.recent_ohlcv
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
        if horizon_params is not None and hasattr(horizon_params, "annualization_factor"):
            annual_factor_sqrt = float(horizon_params.annualization_factor)
        else:
            annual_factor_sqrt = math.sqrt(252.0)

        annual_vol = (
            float(cone.expected_vol_annualized)
            if (cone and cone.expected_vol_annualized > 0)
            else 0.20
        )
        sigma_bar_pct = (annual_vol / max(annual_factor_sqrt, 1.0)) * 100.0

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
