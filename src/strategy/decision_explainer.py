"""Quantitative Decision Explainability Engine.

Produces human-readable, transparent plain-language explanations for accepted trades,
rejected trades, and mandatory 100% cash preservation.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from src.strategy.portfolio_selector import AllocationItem, PortfolioAllocationResult
from src.strategy.trade_ranker import RankedOpportunity

logger = logging.getLogger(__name__)


@dataclass
class PlainLanguageExplanation:
    """Standardized narrative explanation entity for bot activity feeds and telemetry."""

    ticker: str  # Instrument symbol or "PORTFOLIO"
    action: str  # "ACCEPTED", "REJECTED", "HELD_IN_CASH"
    headline: str  # Header for activity feed
    summary: str  # Multi-sentence plain-language explanation
    factors: Dict[str, str]  # Factor name -> descriptive text
    metrics: Dict[str, Any]  # Quantitative verification metrics
    timestamp_utc: str  # UTC ISO timestamp

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
        """Constructs human-readable narrative explanation for an accepted trade opportunity."""
        ev = opportunity.evaluation
        ticker = opportunity.ticker
        direction = opportunity.direction
        win_prob = ev.win_probability * 100.0
        cons_prob = getattr(ev, "conservative_win_prob", ev.win_probability) * 100.0
        ev_pct = ev.net_expectancy_pct
        friction_bps = ev.round_trip_friction_pct * 100.0

        b = max(ev.expected_win_return_pct / max(ev.expected_loss_return_pct, 1e-4), 0.50)
        pt_gain_pct = abs((ev.target_price - ev.entry_price) / max(ev.entry_price, 1e-4)) * 100.0
        sl_loss_pct = abs((ev.entry_price - ev.stop_price) / max(ev.entry_price, 1e-4)) * 100.0

        p_decimals = 4 if ev.entry_price < 10.0 else 2
        pt_fmt = f"{ev.target_price:,.4f}" if p_decimals == 4 else f"{ev.target_price:,.2f}"
        sl_fmt = f"{ev.stop_price:,.4f}" if p_decimals == 4 else f"{ev.stop_price:,.2f}"

        action_word = "BUY" if direction == "LONG" else ("SELL" if direction == "SHORT" else "ENTER")
        headline = f"{action_word} {ticker}: Net Expectancy +{ev_pct:.2f}% | Win Prob {win_prob:.1f}%"
        summary = (
            f"Accepted {direction} opportunity on {ticker}. Model projects a +{ev_pct:.2f}% net mathematical edge "
            f"after deducting {friction_bps:.1f} bps in statutory exchange fees, taxes, and Almgren-Chriss market impact. "
            f"Risk-scaled sizing authorizes {allocation.weight_pct:.1f}% allocation "
            f"({currency_symbol}{allocation.allocated_capital:,.2f} / {allocation.shares:g} units) "
            f"with profit target {currency_symbol}{pt_fmt} and stop loss {currency_symbol}{sl_fmt}."
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
            "entry_price": round(ev.entry_price, p_decimals),
            "target_price": round(ev.target_price, p_decimals),
            "stop_price": round(ev.stop_price, p_decimals),
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
        """Constructs human-readable narrative explanation for a rejected trade candidate."""
        ev = opportunity.evaluation
        ticker = opportunity.ticker
        direction = opportunity.direction
        ev_pct = ev.net_expectancy_pct
        win_prob = ev.win_probability * 100.0
        friction_bps = ev.round_trip_friction_pct * 100.0

        default_reason = (
            "Portfolio Kelly/Volatility Sizing Threshold Not Met"
            if (ev.is_positive_ev and ev_pct >= ev.min_ev_hurdle_pct)
            else "Negative Net Expectancy"
        )
        reason = rejection_reason_override or opportunity.ineligible_reason or ev.rejection_reason or default_reason
        reason_upper = reason.upper()

        if "CRISIS" in reason_upper or opportunity.regime_multiplier == 0.0:
            headline = f"REJECTED {ticker}: Crisis Regime Quarantine"
            summary = (
                f"Rejected {direction} trade on {ticker}. Market is currently in High-Vol Crisis regime (State 2). "
                f"Quantitative risk governance halts new position authorizations to protect capital."
            )
        elif "MICROSTRUCTURE" in reason_upper or "ROLLOVER" in reason_upper or "LULD" in reason_upper:
            headline = f"REJECTED {ticker}: Microstructure Circuit Breaker"
            summary = f"Rejected {direction} trade on {ticker}: {reason}. Trade blocked to prevent severe execution slippage."
        elif ev_pct <= 0.0:
            headline = f"REJECTED {ticker}: Negative Net Expectancy ({ev_pct:.2f}%)"
            summary = (
                f"Rejected {direction} opportunity on {ticker}. Although gross probability is {win_prob:.1f}%, "
                f"net mathematical expectancy is negative ({ev_pct:.2f}%) after deducting {friction_bps:.1f} bps in statutory fees."
            )
        elif ev.is_positive_ev and ev_pct >= ev.min_ev_hurdle_pct:
            headline = f"SKIPPED {ticker}: Below Minimum Portfolio Weight (+{ev_pct:.2f}% EV)"
            summary = (
                f"Candidate {direction} on {ticker} passed Net EV hurdle (+{ev_pct:.2f}%), "
                f"but Fractional Kelly / volatility-adjusted sizing fell below minimum portfolio allocation threshold ({reason})."
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
        """Constructs narrative explanation for the 100% Cash Allocation Guarantee."""
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
        """Generates complete narrative logs across all candidates in a portfolio allocation result."""
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
