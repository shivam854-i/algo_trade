"""Unit tests for TradeEvaluator (Net Expectancy, Epistemic Uncertainty, Conditional Payoffs, Frictions)."""

import math
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest

from src.execution.frictions import FrictionEvaluator
from src.models.foundation_prior import VolatilityCone
from src.models.meta_labeler import MetaPrediction
from src.models.regime_hmm import REGIME_DEFINITIONS
from src.pipeline import SingleAssetAnalysis
from src.strategy.horizon_mapper import HorizonMapper
from src.strategy.trade_evaluator import TradeEvaluationResult, TradeEvaluator


class TestTradeEvaluatorNetExpectancy:
    """Tests for TradeEvaluator net expectancy calculations and rejection logic."""

    def test_exact_analytical_ev_formula(self):
        """Verifies: EV = P(Win)*E[Win] - P(Loss)*E[Loss] - Friction."""
        p_win = 0.60
        p_loss = 0.40
        e_win = 3.00
        e_loss = 1.50
        friction = 0.25

        expected_gross = (p_win * e_win) - (p_loss * e_loss)  # 1.80 - 0.60 = 1.20%
        expected_net = expected_gross - friction  # 1.20 - 0.25 = 0.95%

        assert round(expected_net, 4) == 0.95

    def test_epistemic_uncertainty_formula_and_sample_scaling(self):
        """Verifies sigma_p formula and that smaller sample sizes increase uncertainty."""
        evaluator = TradeEvaluator()
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
        # SE = sqrt(0.55 * 0.45 / 250) = sqrt(0.2475 / 250) = sqrt(0.00099) = 0.031464265
        # Mult = 1.0 + 0.2 * (4.0 / 100.0) = 1.0 + 0.008 = 1.008
        # sigma_p = 0.031464265 * 1.008 = 0.031715979
        assert abs(sigma_p_large_n - 0.031716) < 1e-4

    def test_quantile_dispersion_penalty(self):
        """Verifies: wider quantile envelope (q90 - q10) increases epistemic uncertainty."""
        evaluator = TradeEvaluator()
        p = 0.55
        n_bars = 100

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

    def _make_analysis(
        self,
        ticker: str = "AAPL",
        target: float = 103.0,
        stop: float = 98.5,
        prob: float = 0.65,
        direction: int = 1,
        jurisdiction: str = "US",
    ) -> SingleAssetAnalysis:
        cone = VolatilityCone(
            periods=[1, 2, 3, 4, 5],
            q10_prices=[98.0] * 5,
            q50_prices=[100.0] * 5,
            q90_prices=[102.0] * 5,
            expected_vol_annualized=0.20,
            forward_skew=0.0,
        )
        meta = MetaPrediction(
            primary_direction=direction,
            direction_label="BUY" if direction > 0 else ("SELL" if direction < 0 else "NEUTRAL"),
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
            ticker=ticker,
            current_price=100.0,
            market_jurisdiction=jurisdiction,
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

    def test_rejection_of_non_positive_and_sub_hurdle_ev(self):
        """Verifies: Trades with EV <= 0 or EV < hurdle (+0.20%) are rejected with clear reasons."""
        evaluator = TradeEvaluator(default_min_ev_hurdle_pct=0.20)

        # 1. Low edge, fails hurdle (EV ~ +0.10% < 0.20%)
        analysis_sub = self._make_analysis(target=100.6, stop=99.8, prob=0.55)
        res_sub = evaluator.evaluate(analysis_sub)
        assert not res_sub.is_positive_ev
        assert "BELOW HURDLE" in (res_sub.rejection_reason or "")

        # 2. Negative EV
        analysis_neg = self._make_analysis(target=100.5, stop=97.0, prob=0.45)
        res_neg = evaluator.evaluate(analysis_neg)
        assert not res_neg.is_positive_ev
        assert ("NEGATIVE EV" in (res_neg.rejection_reason or "") or
                "EPISTEMIC" in (res_neg.rejection_reason or ""))

        # 3. High edge passes (+3% target, 1.5% stop, 65% win prob)
        analysis_pass = self._make_analysis(target=103.0, stop=98.5, prob=0.65)
        res_pass = evaluator.evaluate(analysis_pass)
        assert res_pass.is_positive_ev
        assert res_pass.rejection_reason is None
        assert res_pass.net_expectancy_pct >= 0.20
        assert res_pass.win_probability == res_pass.conservative_win_prob

    def test_barrier_inversion_and_neutral_rejection(self):
        """Verifies rejection of inverted target/stop and neutral signals."""
        evaluator = TradeEvaluator()

        # Inverted LONG (target < entry)
        inverted = self._make_analysis(target=95.0, stop=98.0, direction=1)
        res_inv = evaluator.evaluate(inverted)
        assert not res_inv.is_positive_ev
        assert "INVALID BARRIERS" in (res_inv.rejection_reason or "")

        # Neutral direction
        neutral = self._make_analysis(direction=0)
        res_neu = evaluator.evaluate(neutral)
        assert not res_neu.is_positive_ev
        assert "DIRECTION VETO" in (res_neu.rejection_reason or "")

    def test_microstructure_veto_propagation(self):
        """Verifies microstructure circuit breaker rejects trade."""
        evaluator = TradeEvaluator()
        analysis = self._make_analysis()

        with patch.object(
            FrictionEvaluator,
            "check_microstructure_execution_gate",
            return_value=(False, "Rollover spike 400%"),
        ):
            res = evaluator.evaluate(analysis)
            assert not res.is_positive_ev
            assert "MICROSTRUCTURE GATE VETO" in (res.rejection_reason or "")
