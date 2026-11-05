"""Trade Opportunity Ranking Module.

Ranks evaluated trade opportunities by risk-adjusted net expectancy, applies market
regime alignment multipliers (State 0 Trending, State 1 Choppy, State 2 Crisis hard veto),
and adds model synergy boosts for Causal TCN and Meta-Labeler consensus.
"""

from dataclasses import asdict, dataclass
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.models.regime_hmm import RegimeState
from src.pipeline import SingleAssetAnalysis
from src.strategy.trade_evaluator import TradeEvaluationResult

logger = logging.getLogger(__name__)


@dataclass
class RankedOpportunity:
    """Systematically ranked trade opportunity ready for portfolio allocation."""

    rank: int  # 1-indexed rank
    ticker: str
    direction: str  # "LONG" or "SHORT"
    evaluation: TradeEvaluationResult
    risk_adjusted_value: float  # EV / max(sigma_asset, 0.05)
    regime_multiplier: float  # 1.25 (Trending), 1.15 (Choppy), 0.0 (Crisis veto), 1.0 (Neutral)
    synergy_boost: float  # 1.15 (TCN + Meta agreement) or 1.0
    composite_score: float  # risk_adjusted_value * regime_multiplier * synergy_boost
    is_eligible: bool  # True if eligible for capital allocation
    ineligible_reason: Optional[str] = None  # Reason if ineligible, else None
    rank_justification: str = ""  # Plain-language explanation

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["evaluation"] = self.evaluation.to_dict()
        return d


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
        if regime.state_id == 2 or getattr(regime, "is_crisis", False):
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
