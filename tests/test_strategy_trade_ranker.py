"""Unit tests for TradeRanker (Risk-adjusted value, Regime multipliers, Synergy boosts, Sorting)."""

import pandas as pd
import pytest

from src.models.foundation_prior import VolatilityCone
from src.models.meta_labeler import MetaPrediction
from src.models.regime_hmm import REGIME_DEFINITIONS, RegimeState
from src.pipeline import SingleAssetAnalysis
from src.strategy.trade_evaluator import TradeEvaluationResult
from src.strategy.trade_ranker import RankedOpportunity, TradeRanker


class TestTradeRanker:
    """Tests for TradeRanker multi-factor ranking, regime filtering, and synergy boosts."""

    def _make_eval(self, ticker: str, net_ev: float, is_pos: bool, vol: float = 0.20, direction: str = "LONG"):
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

    def test_model_synergy_boost(self):
        """Verifies: 1.15x synergy boost when Causal TCN and Meta-Labeler agree strongly."""
        ranker = TradeRanker()
        ev = self._make_eval("MSFT", net_ev=1.0, is_pos=True, vol=0.20, direction="LONG")

        # Create mock SingleAssetAnalysis with neural_prob >= 0.60
        cone = VolatilityCone(
            periods=[1, 2],
            q10_prices=[98.0, 98.0],
            q50_prices=[100.0, 100.0],
            q90_prices=[102.0, 102.0],
            expected_vol_annualized=0.20,
            forward_skew=0.0,
        )
        meta = MetaPrediction(
            primary_direction=1,
            direction_label="BUY",
            success_probability=0.65,
            bet_size=0.10,
            target_price=103.0,
            stop_price=98.5,
            feature_importances={},
        )
        analysis_boost = SingleAssetAnalysis(
            ticker="MSFT",
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
            recent_ohlcv=pd.DataFrame(),
            features_df=pd.DataFrame(),
            neural_prob=0.70,  # Strongly agrees with LONG
        )

        ranked = ranker.rank_opportunities([ev], analyses={"MSFT": analysis_boost})
        assert ranked[0].synergy_boost == 1.15
        # composite_score = risk_adj (5.0) * regime (1.25) * synergy (1.15) = 7.1875
        assert abs(ranked[0].composite_score - 7.1875) < 1e-3

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
        assert ranked[0].rank == 1
        assert ranked[1].rank == 2
        assert ranked[2].rank == 3
        assert ranked[3].rank == 4

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

    def test_serialization(self):
        """Verifies RankedOpportunity dictionary serialization."""
        ev = self._make_eval("NVDA", net_ev=1.2, is_pos=True)
        ranker = TradeRanker()
        ranked = ranker.rank_opportunities([ev])
        d = ranked[0].to_dict()
        assert d["ticker"] == "NVDA"
        assert d["is_eligible"] is True
        assert "evaluation" in d
